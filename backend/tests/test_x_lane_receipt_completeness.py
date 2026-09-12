"""An X-lane receipt carries P1-P6, LAP and the anonymisation gap, or the board
refuses it.

Spec `docs/research_notes/2026-09-12/spec_lane_x.md` section 6 and MUST NOT
REGRESS #24. Three properties are pinned here:

1. the validator names the MISSING FIELD, not "invalid block" -- a refusal a
   reader cannot act on is the same skimmed red line as `0/9 stamped [FAIL]`;
2. `night_leaderboard_sync` actually calls it -- checked on the AST of the
   function BODY, because a grep that matches the docstring explaining the
   guard is a broken guard (CLAUDE.md session protocol 10);
3. every X-lane receipt ON DISK passes -- so a job that starts writing an
   incomplete receipt turns the suite red the same night.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from backend.services import protocol_p16 as pp

REPO = Path(__file__).resolve().parents[2]


def _complete() -> dict:
    """A receipt that passes. Every other case in this file mutates a copy."""
    return {
        "job": "X2_elasticity", "lane": "X", "licence": "PRODUCT_EXPERIMENT",
        "P1_P6": pp.block(
            anonymised=True, anonymised_evidence="C1_counterfactual_news.jsonl",
            placebo_run=True, placebo_evidence="x2_placebo_pairs.jsonl",
            time_locked_run=False,
            cutoff="2024-06-30", cutoff_source="community cutoff tracker",
            cutoff_confidence="MEDIUM",
            universe_vintage_id="P7_pit_universe_vintage_run01",
            delisting_handled=True, universe_note="P7 vintage",
            flip_pass_rate=0.61, flip_n=120,
            ece=0.08, n_bins=10, brier=0.24,
            brier_decomposition={"reliability": 0.01, "resolution": 0.02,
                                 "uncertainty": 0.25},
            cost_curve_id="r2_trial.COST_BPS_PER_SIDE",
            cost_bps_per_side=25.0, realised_bps=11.3,
            field_provenance={"direction": "Qwen2.5-7B via the frozen R2 prompt"}),
        "LAP": pp.lap(False, reason="post-cutoff panel, LAP not required per section 1.3"),
        "anonymisation_gap": pp.anonymisation_gap(reason="no anonymised-text arm"),
    }


def test_a_complete_receipt_passes():
    assert pp.validate(_complete()) == []
    assert pp.refuse_reasons("X2_elasticity", _complete()) == []


@pytest.mark.parametrize("key", pp.P_KEYS)
def test_a_receipt_missing_one_protocol_item_is_refused_naming_it(key):
    r = _complete()
    del r["P1_P6"][key]
    reasons = pp.validate(r)
    assert reasons, f"dropping {key} was not noticed"
    assert any(key in reason for reason in reasons), reasons


@pytest.mark.parametrize("key,field", [(k, f) for k, fs in pp.REQUIRED_FIELDS.items()
                                       for f in fs])
def test_a_receipt_missing_one_subfield_is_refused_naming_the_field(key, field):
    r = _complete()
    del r["P1_P6"][key][field]
    reasons = pp.validate(r)
    assert any(f"{key}.{field}" in reason for reason in reasons), (key, field, reasons)


def test_the_whole_block_missing_is_one_reason_not_six():
    r = _complete()
    del r["P1_P6"]
    assert "P1_P6: the block is missing entirely" in pp.validate(r)


def test_lap_not_applicable_without_a_reason_is_refused():
    """Spec section 6: an explicit non-applicability passes, a bare omission does not."""
    r = _complete()
    r["LAP"] = {"applies": False, "reason_if_not_applicable": ""}
    assert any("reason_if_not_applicable" in x for x in pp.validate(r))
    r["LAP"] = {"applies": False, "reason_if_not_applicable": "PANEL-B is post-cutoff"}
    assert pp.validate(r) == []


def test_lap_missing_entirely_is_refused():
    r = _complete()
    del r["LAP"]
    assert any(x.startswith("LAP:") for x in pp.validate(r))


def test_lap_that_applies_needs_a_score_or_a_verdict():
    r = _complete()
    r["LAP"] = pp.lap(True)
    assert any("LAP.score" in x for x in pp.validate(r))
    r["LAP"] = pp.lap(True, score=0.12)
    assert pp.validate(r) == []
    r["LAP"] = pp.lap(True, verdict="NOT_A_VERDICT")
    assert any("study_verdict" in x for x in pp.validate(r))


def test_anonymisation_gap_null_without_a_reason_is_refused():
    r = _complete()
    r["anonymisation_gap"] = {"value_pct_pt": None}
    assert any("anonymisation_gap.reason" in x for x in pp.validate(r))
    r["anonymisation_gap"] = pp.anonymisation_gap(1.2, t=0.4, adopted_arm="MASKED")
    assert pp.validate(r) == []


def test_a_control_claimed_true_with_no_evidence_path_is_refused():
    """`anonymised: true` with nothing behind it is the failure this enforces."""
    r = _complete()
    r["P1_P6"]["P1_temporal_integrity"]["evidence_paths"]["anonymised"] = None
    reasons = pp.validate(r)
    assert any("evidence_paths.anonymised" in x for x in reasons), reasons
    # and a control that did NOT run is honest with a null path
    r2 = _complete()
    r2["P1_P6"]["P1_temporal_integrity"]["date_shifted_placebo_run"] = False
    r2["P1_P6"]["P1_temporal_integrity"]["evidence_paths"]["date_shifted_placebo_run"] = None
    assert pp.validate(r2) == []


def test_a_flip_rate_over_zero_cells_is_refused():
    r = _complete()
    r["P1_P6"]["P3_direction_flip"] = {"pass_rate": 0.5, "n": 0, "test": "x"}
    assert any("P3_direction_flip.n" in x for x in pp.validate(r))


def test_a_cost_rate_without_its_curve_is_refused():
    r = _complete()
    r["P1_P6"]["P5_full_frictions"]["cost_curve_id"] = ""
    assert any("cost_curve_id" in x for x in pp.validate(r))


# ---------------------------------------------------------------- the trigger

@pytest.mark.parametrize("job,bound", [
    ("X2_elasticity", True), ("X_anon_gap", True), ("X4_regime_route", True),
    ("L3_lookahead", True),
    ("R2_widened_panelB", False), ("D1_reaction_book", False),
    ("G3_evolve_v2", False), ("N3_frozen_embedding_head", False),
    ("E1_news_return_panel", False), ("RW1_random_windows", False),
])
def test_which_jobs_the_protocol_binds(job, bound):
    assert pp.is_x_lane(job, {}) is bound


def test_a_declared_lane_binds_whatever_the_job_is_called():
    assert pp.is_x_lane("R2_widened_panelB", {"lane": "X"}) is True


def test_a_non_x_receipt_is_never_refused_by_this_protocol():
    assert pp.refuse_reasons("D1_reaction_book", {"job": "D1_reaction_book"}) == []


# ------------------------------------------------- the leaderboard's own call

def _fn_source(module_path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in {module_path}")


def _calls(fn: ast.FunctionDef) -> set[str]:
    """Names called in the BODY, docstring excluded by construction (an AST
    carries no comments and a docstring is an expression, never a Call)."""
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


@pytest.mark.parametrize("fn_name", ["main", "rebuild"])
def test_the_leaderboard_sync_calls_the_completeness_check(fn_name):
    """AST, not grep: the guard must be CALLED, not merely mentioned."""
    sync = REPO / "scripts" / "night_leaderboard_sync.py"
    fn = _fn_source(sync, fn_name)
    assert "protocol_refusal" in _calls(fn), (
        f"{fn_name}() appends leaderboard rows without calling protocol_refusal; "
        "an X-lane receipt would reach the board without its P1-P6 block")


def test_the_sync_refusal_names_the_missing_field(capsys):
    import scripts.night_leaderboard_sync as sync

    r = _complete()
    del r["P1_P6"]["P4_calibration_ece"]
    msg = sync.protocol_refusal("X2_elasticity", r)
    assert msg and "P4_calibration_ece" in msg
    assert sync.protocol_refusal("X2_elasticity", _complete()) is None
    assert sync.protocol_refusal("D1_reaction_book", {"verdict": "x"}) is None


# ------------------------------------------------- every receipt already on disk

def _x_lane_receipts() -> list[Path]:
    base = REPO / "backend" / "data" / "optimus"
    if not base.is_dir():
        return []
    # THE BOARD'S OWN PATTERN, not a looser glob: a sidecar the board never
    # reads as a receipt must not be held to a receipt's schema here either,
    # or the two disagree about what a receipt is.
    from scripts.night_leaderboard_sync import RECEIPT

    out = []
    for night in sorted(base.glob("night_factory_*")):
        for p in sorted(night.glob("*_run*.json")):
            m = RECEIPT.match(p.name)
            if not m or p.name.endswith("_smoke.json"):
                continue
            if pp.X_JOB_RE.match(m.group("job")):
                out.append(p)
    return out


def test_every_x_lane_receipt_on_disk_carries_the_protocol():
    bad = []
    for p in _x_lane_receipts():
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  an unreadable receipt is a finding
            bad.append(f"{p.name}: unreadable ({type(exc).__name__})")
            continue
        reasons = pp.refuse_reasons(p.name.split("_run")[0], payload)
        if reasons:
            bad.append(f"{p.name}: " + "; ".join(reasons))
    assert not bad, "\n".join(bad)


def test_the_builder_emits_every_required_key():
    """A block straight out of `pp.block` carries every required KEY -- so the
    only thing a validator can complain about is a VALUE the job failed to
    measure, never a field the constructor forgot. Otherwise the constructor
    and the checker drift and six writers each patch the gap differently."""
    bare = pp.block(anonymised=False)
    for key, fields in pp.REQUIRED_FIELDS.items():
        assert key in bare
        for field in fields:
            assert field in bare[key], f"pp.block() omits {key}.{field}"
    # a job that priced no book says so, and the block passes
    r = {"job": "X9_probe",
         "P1_P6": pp.block(anonymised=False, costed=False,
                           cost_curve_id="none: this job prices no book",
                           field_provenance={"none": "no model call in this job"}),
         "LAP": pp.lap(False, reason="no LLM read in this job"),
         "anonymisation_gap": pp.anonymisation_gap(reason="no anonymised-text arm")}
    assert pp.validate(r) == []


def test_assert_valid_raises_with_every_reason():
    r = _complete()
    del r["P1_P6"]["P2_dynamic_universe"]
    del r["LAP"]
    with pytest.raises(pp.ProtocolIncomplete) as exc:
        pp.assert_valid("X2_elasticity", r)
    assert "P2_dynamic_universe" in str(exc.value) and "LAP" in str(exc.value)


def test_ece_is_computed_on_the_same_bins_as_the_brier_split():
    import numpy as np

    rng = np.random.default_rng(20260912)
    p = rng.uniform(0, 1, 400)
    o = (rng.uniform(0, 1, 400) < p).astype(float)     # a well-calibrated forecaster
    out = pp.ece(p, o, n_bins=10)
    assert out["ece"] is not None and 0.0 <= out["ece"] < 0.15
    assert out["n_bins"] == len(out["bins"])
    assert set(pp.BRIER_TERMS) <= set(out["brier_decomposition"])
    # a miscalibrated one scores worse on the same partition
    bad = pp.ece(np.clip(p * 0.2, 0, 1), o, n_bins=10)
    assert bad["ece"] > out["ece"]


def test_ece_on_a_sample_too_small_to_bin_refuses_rather_than_inventing():
    out = pp.ece([0.5, 0.5], [1.0, 0.0], n_bins=10)
    assert out["ece"] is None and out["note"]


def test_a_deep_copy_of_the_complete_receipt_is_json_round_trippable():
    r = _complete()
    assert pp.validate(json.loads(json.dumps(copy.deepcopy(r)))) == []
