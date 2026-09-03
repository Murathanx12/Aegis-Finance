"""The Capital Allocator v0 properties that must never quietly stop being true.

Born from the idle two-thirds (REVIEW 2026-09-03 PART B: hack3/4/6 sat 60-67%
cash with no opinion recorded) and from the invisible 40% ceiling
(FINDING 2026-09-04, terminal repo: a taxonomy gap became a fleet-wide
position limit and no surface named the binding constraint). So these tests
pin the DECISION-VISIBILITY properties, not forecast accuracy:

1. the residual row ALWAYS exists and weights (allocations + residual) sum to
   the gross cap -- every unused dollar is documented;
2. cash NEVER wins by default: a positive cash margin without an explicit
   thesis is recorded, not funded; a thesis that fails the numbers is refused;
3. a gated sleeve appears at weight 0 WITH its gate named -- it never vanishes
   from the table;
4. every number in u_components is cited (path#key), a DEFINITION, PRIOR_ONLY,
   derived from such, or a REFUSAL naming the missing input -- never a bare
   number;
5. binding_constraints is populated for every sleeve plus the gross cap --
   a weight without its binding reason is a lie of omission;
6. no broker/execution import can reach the allocator (hard boundary, in
   source, not in prose);
7. a missing receipt is a NAMED refusal, never a zero;
8. the revision sleeve carries BOTH the pooled and the 2022-24 adverse-era
   excess rows (contract section 0: never the pooled alone).

Offline, synthetic PotentialUniverse + synthetic receipts mirroring the real
key paths, dates DERIVED from today (a fixture that hard-codes a calendar
moment fails the day after that moment passes).
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from datetime import date, timedelta
from pathlib import Path

import pytest

from learner import allocator as A

# ------------------------------------------------------------------ fixtures


def _recent_day() -> str:
    d = date.today() - timedelta(days=7)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


DAY = _recent_day()


def _receipts() -> dict:
    """Synthetic receipts mirroring the REAL key paths, so the extraction
    code under test is the same code the real run exercises."""
    rev_arm = {"excess_cagr": 0.0175, "t_paired_vs_vw": 0.73,
               "max_drawdown": -0.3903, "implied_annual_cost_drag_pct": 0.951,
               "market_cagr": 0.1265}
    return {
        "revision_6m": {
            "arms": {A.REV_ARM: rev_arm},
            "subwindow_2022_2024": {
                A.REV_ARM: {"excess_cagr": -0.014, "t_paired_vs_vw": -0.047}},
            "null_vs_random_from_pool": {
                "metrics": {"monthly_excess_mean_pct": {"p_one_sided": 0.0154}}},
        },
        "learner_v2": {
            "champions": {"1m": {"tradable_floor_variant": {
                "annualised_excess": 0.18,
                "t_stat_paired_vs_market": 2.866,
                "risk": {"max_drawdown_net": -0.2899,
                         "cvar_05_monthly": -0.1455,
                         "max_drawdown_market_same_months": -0.3331}}}},
            "model_null_distribution": {"horizons": {"1m": {"arms": {
                "encoder_clf__residual": {
                    "p_vs_model_null_paired_t": 0.0154}}}}},
        },
        "learner_v1_null": {
            "model_null_64_20260904": {"arms": {"lgbm_clf": {
                "verdict_paired_t": {"verdict": "CLEARS_MODEL_NULL"}}}}},
        "toxic_short": {
            "verdict_headline_1m": {"naive_short": {
                "gross_annualised_pct": 32.348,
                "breakeven_borrow_pct_25bps": 27.34}},
            "conventions": {
                "borrow_note": "NO borrow-rate data exists in this repo."}},
    }


def _pu(day: str = DAY) -> dict:
    return {
        "header": {
            "status": "OK", "day": day,
            "version": "potential_universe_v1/synthetic",
            "counts": {
                "n_scorecards": 3,
                "by_engine_verdict": {"admitted_shadow": 2, "toxic_ge_5": 1},
                "by_capacity_tier": {"FULL": 3},
                "d_catalyst_unreadable": 1},
            "whole_universe_refusals": {
                "learner_v2": {"refused_on": 3, "of": 3,
                               "missing_inputs": ["x"]}},
        },
        "scorecards": [],
    }


def _build(personality: str = "balanced", *, receipts=None, cash_thesis=None,
           day: str = DAY):
    return A.build_decision_artifact(
        day, personality,
        pu=_pu(day),
        receipts=_receipts() if receipts is None else receipts,
        cash_thesis=cash_thesis)


def _row(artifact: dict, sleeve: str) -> dict:
    return next(r for r in artifact["allocations"] if r["sleeve"] == sleeve)


# ------------------------------------------- 1. residual + weight discipline


@pytest.mark.parametrize("personality", sorted(A.PERSONALITIES))
def test_residual_row_always_exists_and_weights_sum_to_gross_cap(personality):
    art = _build(personality)
    res = art["residual"]
    assert res["sleeve"] == "__residual__"
    assert res["destination"] in ("benchmark_SPY", "cash")
    assert res["rationale"]
    total = sum(r["weight"] for r in art["allocations"]) + res["weight"]
    assert total == pytest.approx(A.GROSS_CAP, abs=1e-9)
    assert all(r["weight"] >= 0 for r in art["allocations"])


def test_residual_is_total_when_every_receipt_is_unreadable():
    """No receipts -> no sleeve can price itself -> the WHOLE book is the
    residual row, parked in the benchmark. Idle-by-ignorance is still a
    documented decision, never a silent 0% deployment."""
    art = _build(receipts={k: None for k in A.RECEIPT_PATHS})
    assert art["residual"]["weight"] == pytest.approx(A.GROSS_CAP)
    assert art["residual"]["destination"] == "benchmark_SPY"
    for r in art["allocations"]:
        assert r["weight"] == 0.0
        assert r["binding_constraint"]


# --------------------------------------------------- 2. cash needs a thesis


def test_cash_never_wins_by_default():
    """Under preservation lambdas cash's margin vs the benchmark is POSITIVE
    (the drawdown penalty does that) -- and cash still gets nothing without a
    thesis. The near-win is recorded, not funded."""
    art = _build("preservation")
    assert art["cash_policy"]["cash_wins_numerically"] is True
    assert _row(art, "cash")["weight"] == 0.0
    assert "NO_THESIS" in _row(art, "cash")["binding_constraint"]
    assert art["residual"]["destination"] == "benchmark_SPY"


def test_cash_with_thesis_and_positive_margin_takes_the_residual():
    thesis = "explicit deleveraging thesis for the test book"
    art = _build("preservation", cash_thesis=thesis)
    assert art["residual"]["destination"] == "cash"
    assert art["residual"]["thesis"] == thesis
    assert art["cash_policy"]["thesis_supplied"] == thesis
    total = sum(r["weight"] for r in art["allocations"]) + art["residual"]["weight"]
    assert total == pytest.approx(A.GROSS_CAP, abs=1e-9)


def test_thesis_alone_cannot_fund_cash_when_the_numbers_refuse():
    """balanced lambdas: cash loses to the benchmark, so even an explicit
    thesis is recorded-and-refused. Necessary AND sufficient, both required."""
    art = _build("balanced", cash_thesis="bearish, but the numbers disagree")
    assert art["cash_policy"]["cash_wins_numerically"] is False
    assert art["residual"]["destination"] == "benchmark_SPY"
    assert "THESIS_REFUSED" in _row(art, "cash")["binding_constraint"]


# ------------------------------------------------ 3. gated sleeve stays seen


def test_gated_sleeve_appears_weight_zero_with_its_gate_named():
    art = _build("aggressive")
    row = _row(art, "toxic_band_short")
    assert row["weight"] == 0.0
    assert row["gate"] == "NOT_DEPLOYABLE_NO_BORROW_DATA"
    assert "NOT_DEPLOYABLE_NO_BORROW_DATA" in row["binding_constraint"]
    # the gate's reason names the missing input, not just a verdict
    assert "borrow" in row["u_components"]["e_excess"]["reason"].lower()


# ---------------------------------------- 4. every number cited or declared


_OK_BASES = {"cited", "DEFINITION", "PRIOR_ONLY", "derived", "REFUSED"}


def _assert_component(path: str, c: dict):
    assert isinstance(c, dict) and "basis" in c, f"{path}: bare value"
    basis = c["basis"]
    assert basis in _OK_BASES, f"{path}: unknown basis {basis!r}"
    if basis == "cited":
        assert c.get("source"), f"{path}: cited without a source"
        assert "#" in c["source"], f"{path}: source lacks path#key form"
    elif basis == "REFUSED":
        assert c.get("reason"), f"{path}: refusal without a named reason"
        assert c.get("value") is None, f"{path}: a refusal carrying a value"
    elif basis in ("PRIOR_ONLY", "DEFINITION", "derived"):
        assert c.get("note"), f"{path}: {basis} without its rationale"
    for k, sub in (c.get("sub_components") or {}).items():
        _assert_component(f"{path}.{k}", sub)


@pytest.mark.parametrize("personality", ["balanced", "aggressive"])
def test_every_u_component_is_cited_prior_only_or_refused(personality):
    art = _build(personality)
    for r in art["allocations"]:
        for name, c in r["u_components"].items():
            _assert_component(f"{r['sleeve']}.{name}", c)
    assert "PRIOR_ONLY" in art["lambdas"]["basis"]
    assert art["missing_inputs_v1_must_replace"]


# ------------------------------------------- 5. binding constraints visible


@pytest.mark.parametrize("personality", sorted(A.PERSONALITIES))
def test_binding_constraints_populated_for_every_sleeve_and_gross(personality):
    art = _build(personality)
    for r in art["allocations"]:
        assert isinstance(r["binding_constraint"], str) and r["binding_constraint"], \
            f"{r['sleeve']}: weight without a binding reason"
    named = {b["sleeve"] for b in art["binding_constraints"]}
    assert named == {r["sleeve"] for r in art["allocations"]} | {"__gross__"}


def test_a_capped_sleeve_names_the_cap_as_binding():
    art = _build("balanced")
    row = _row(art, "learner_v2_monthly")
    assert row["weight"] == pytest.approx(
        A.PERSONALITIES["balanced"]["max_sleeve_weight"])
    assert "MAX_SLEEVE_WEIGHT" in row["binding_constraint"]


# ------------------------------------------------------- 6. hard boundary


REPO = Path(__file__).resolve().parents[2]
_FORBIDDEN = re.compile(
    r"alpaca|submit_order|brokerage|aegis-alpha-terminal|alpha\.universe"
    r"|alpha\.brains|TradingClient|OrderRequest",
    re.IGNORECASE)
_STDLIB_OK = {"__future__", "hashlib", "json", "datetime", "pathlib", "typing"}


def _scannable_source(src: str) -> str:
    """Code plus NON-DOCSTRING string literals. Docstrings may cite the
    execution repo's finding documents (that lineage is wanted); a broker
    path or client name would live in code or in a working string literal,
    and those are exactly what gets scanned."""
    tree = ast.parse(src)
    doc_nodes: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (body and isinstance(node, (ast.Module, ast.FunctionDef,
                                       ast.AsyncFunctionDef, ast.ClassDef))
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            doc_nodes.add(id(body[0].value))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in doc_nodes]
    code_tokens = [t.string
                   for t in tokenize.generate_tokens(io.StringIO(src).readline)
                   if t.type not in (tokenize.STRING, tokenize.COMMENT)]
    return " ".join(code_tokens + literals)


@pytest.mark.parametrize("rel", ["learner/allocator.py",
                                 "scripts/allocator_run.py"])
def test_no_broker_or_execution_import_in_source(rel):
    src = (REPO / rel).read_text(encoding="utf-8")
    hit = _FORBIDDEN.search(_scannable_source(src))
    assert hit is None, f"{rel}: forbidden token {hit.group(0)!r}"
    assert "SHADOW_ONLY" in src or "SHADOW ONLY" in src


def test_allocator_module_is_stdlib_only():
    """The stdlib-only import block IS the boundary audit; pin it so a future
    convenience import (pandas today, a client tomorrow) fails loudly."""
    src = (REPO / "learner" / "allocator.py").read_text(encoding="utf-8")
    roots: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert roots <= _STDLIB_OK, f"non-stdlib imports crept in: {roots - _STDLIB_OK}"


def test_authority_field_is_verbatim():
    art = _build()
    assert art["authority"].startswith("SHADOW_ONLY")
    assert "places nothing" in art["authority"]
    assert art["licence"] == "PRODUCT_EXPERIMENT (shadow)"


# ---------------------------------------- 7. missing receipt = named refusal


def test_missing_receipt_is_a_named_refusal_never_a_zero():
    receipts = _receipts()
    receipts["revision_6m"] = None
    art = _build("aggressive", receipts=receipts)
    row = _row(art, "revision_6m")
    assert row["gate"] == "NOT_DEPLOYABLE_RECEIPT_UNREADABLE"
    assert row["weight"] == 0.0
    assert row["U"] is None                    # unpriceable, not zero-utility
    e = row["u_components"]["e_excess"]
    assert e["basis"] == "REFUSED"
    assert "revision_6m_cohorts_20260904.json" in e["reason"]


def test_missing_key_inside_a_receipt_refuses_and_names_the_key():
    receipts = _receipts()
    del receipts["learner_v2"]["champions"]["1m"]["tradable_floor_variant"][
        "annualised_excess"]
    art = _build(receipts=receipts)
    e = _row(art, "learner_v2_monthly")["u_components"]["e_excess"]
    assert e["basis"] == "REFUSED"
    assert "annualised_excess" in e["reason"]


# --------------------------------- 8. the adverse era travels with the pooled


def test_revision_sleeve_carries_both_pooled_and_adverse_era_rows():
    art = _build()
    c = _row(art, "revision_6m")["u_components"]
    assert c["e_excess"]["basis"] == "cited"
    assert c["e_excess"]["value"] == pytest.approx(0.0175)
    assert c["e_excess_2022_2024"]["basis"] == "cited"
    assert c["e_excess_2022_2024"]["value"] == pytest.approx(-0.014)
    assert "2022_2024" in c["e_excess_2022_2024"]["source"]
    # and the era gap is a NUMBER inside the uncertainty term, not prose
    era = c["uncertainty"]["sub_components"]["era_dispersion"]
    assert era["value"] == pytest.approx(0.0175 - (-0.014))


def test_v2_borrowed_era_dispersion_is_marked_prior_only():
    art = _build()
    c = _row(art, "learner_v2_monthly")["u_components"]
    era = c["uncertainty"]["sub_components"]["era_dispersion"]
    assert era["basis"] == "PRIOR_ONLY"
    assert "MISSING" in era["note"]


# ------------------------------------------------------ artifact mechanics


def test_artifact_and_row_schemas_are_golden():
    art = _build()
    assert set(art.keys()) == set(A.ARTIFACT_KEYS)
    for r in art["allocations"]:
        assert set(r.keys()) == set(A.ALLOCATION_ROW_KEYS)
    assert art["schema"]["schema_hash"] == A.schema_hash()


def test_worst_case_is_printed_in_dollars():
    art = _build("balanced")
    wc = art["worst_case"]
    assert wc["worst_case_usd"] < 0
    assert wc["equity_usd_assumed"] == 100_000.0
    assert wc["terms"], "no worst-case terms: the number came from nowhere"
    frac = sum(t["weight"] * t["maxdd_proxy"] for t in wc["terms"])
    assert wc["worst_case_fraction"] == pytest.approx(frac, abs=1e-6)


def test_regret_spec_names_all_seven_components_and_its_missing_input():
    spec = _build()["regret_decomposition_spec"]
    assert set(spec["components"]) == {
        "selection_alpha", "beta_gap", "sizing", "timing", "cash_drag",
        "execution", "risk_interventions"}
    assert "MISSING" in spec["inputs_required"]["sleeve_betas"]


def test_write_and_reload_roundtrip(tmp_path):
    art = _build("aggressive")
    path = A.write_decision_artifact(art, out_dir=tmp_path)
    assert path.name == f"{DAY}_aggressive.json"
    back = json.loads(path.read_text(encoding="utf-8"))
    total = sum(r["weight"] for r in back["allocations"]) + back["residual"]["weight"]
    assert total == pytest.approx(A.GROSS_CAP, abs=1e-9)
    assert back["authority"].startswith("SHADOW_ONLY")


def test_universe_refusal_is_visible_in_the_artifact():
    """No PotentialUniverse -> the artifact SAYS so instead of pretending the
    universe was empty (absence of the input is not evidence about the world)."""
    art = A.build_decision_artifact(DAY, "balanced", pu=None,
                                    receipts=_receipts())
    assert art["universe"]["status"] == "REFUSED"
    assert "unknowable" in art["universe"]["reason"]


def test_unknown_personality_refuses():
    with pytest.raises(ValueError, match="unknown personality"):
        A.build_decision_artifact(DAY, "yolo", pu=_pu(), receipts=_receipts())
