"""X2: the elasticity arithmetic, the flip test, and a placebo that is ~0.

Spec section 7 step 4's known answers come first: `p_real = -0.6`, `p_cf = +0.6`,
`delta = +2` must give elasticity exactly 0.6 with `flip_pass == 1`; a pair
where the forecast does not move at all must FAIL the flip test rather than
count as a tie.

The rest are about what gets DROPPED. The spec proposed a fixed `delta = +1`
for escalations and asked for it to be checked; counted over C1 it is wrong for
18% of them, and a formula that forces those to +1 would put a denominator
under a perturbation that has none.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from backend.services import belief_elasticity as be
from backend.services import protocol_p16 as pp
from scripts import night_x2_elasticity as X2


def test_the_specs_own_known_answer():
    """p_real -0.6, p_cf +0.6, a clean DOWN-to-UP flip."""
    delta = be.delta_event("sign_flip", "NEGATIVE", "POSITIVE")
    assert delta == 2.0
    assert be.elasticity(-0.6, 0.6, delta) == pytest.approx(0.6)
    assert be.flip_pass(-0.6, 0.6, delta) == 1


def test_a_forecast_that_does_not_move_fails_the_flip_test():
    """A tie is a FAIL: a model unmoved by a sign-flipped input is not
    demonstrating sensitivity to content."""
    delta = be.delta_event("sign_flip", "POSITIVE", "NEGATIVE")
    assert be.flip_pass(0.4, 0.4, delta) == 0
    assert be.elasticity(0.4, 0.4, delta) == 0.0


def test_a_forecast_that_moves_the_WRONG_way_fails():
    delta = be.delta_event("sign_flip", "NEGATIVE", "POSITIVE")   # +2
    assert be.flip_pass(0.5, -0.5, delta) == 0
    assert be.elasticity(0.5, -0.5, delta) == pytest.approx(-0.5)


@pytest.mark.parametrize("parent,cf,expect", [
    ("POSITIVE", "NEGATIVE", -2.0),
    ("NEGATIVE", "POSITIVE", 2.0),
    ("UNCLEAR", "NEGATIVE", None),      # no parent sign: no denominator
    ("POSITIVE", "UNCLEAR", None),
    ("NEGATIVE", "NEGATIVE", None),     # a "flip" that did not flip
    (None, "POSITIVE", None),
])
def test_sign_flip_denominators(parent, cf, expect):
    assert be.delta_event("sign_flip", parent, cf) == expect


@pytest.mark.parametrize("parent,cf,expect", [
    ("POSITIVE", "POSITIVE", 1.0),      # more of the same, in the parent's frame
    ("NEGATIVE", "NEGATIVE", -1.0),
    ("POSITIVE", "NEGATIVE", None),     # 18% of C1's escalations: no scale
    ("UNCLEAR", "POSITIVE", None),
])
def test_escalation_denominators_are_measured_not_fixed(parent, cf, expect):
    """The spec proposed `+1 fixed` and flagged it for re-verification. Counted
    over all 6,935 C1 rows on 2026-09-12: 4,919 escalations agree with their
    parent's direction and 1,107 (18.37%) do not. A fixed +1 would put a
    denominator under a perturbation that has none."""
    assert be.delta_event("escalation", parent, cf) == expect


def test_actor_timing_has_no_elasticity_at_all():
    assert be.delta_event("actor_timing", "POSITIVE", "NEGATIVE") is None
    assert "actor_timing" in be.DIAGNOSTIC_ONLY_KINDS
    assert "actor_timing" not in be.ELASTIC_KINDS


def test_a_zero_denominator_returns_none_not_infinity():
    assert be.elasticity(0.5, -0.5, 0) is None
    assert be.elasticity(0.5, -0.5, None) is None
    assert be.flip_pass(0.5, -0.5, 0) is None


@pytest.mark.parametrize("d,c,expect", [
    (1, 0.7, 0.7), (-1, 0.7, -0.7), (0, 0.7, 0.0), (None, 0.7, 0.0),
    ("POSITIVE", 0.4, 0.4), ("NEGATIVE", 0.4, -0.4), ("UNCLEAR", 0.4, 0.0),
    (1, 1.9, 1.0),                       # clipped, not trusted
])
def test_the_signed_scalar_matches_r2s_parser_convention(d, c, expect):
    assert be.signed_p(d, c) == pytest.approx(expect)


# --------------------------------------------------------------- the pairing

def _c1_rows():
    return [
        {"uid": "u1", "status": "OK", "anon": "the co beat", "direction": "POSITIVE",
         "effective_at": "2025-03-04", "symbols": ["AAA"], "event_type": "EARNINGS",
         "counterfactuals": [
             {"kind": "sign_flip", "text": "the co missed", "direction": "NEGATIVE"},
             {"kind": "escalation", "text": "the co crushed", "direction": "POSITIVE"},
             {"kind": "actor_timing", "text": "a rival beat", "direction": "NEGATIVE"}]},
        {"uid": "u2", "status": "OK", "anon": "the co was sued", "direction": "NEGATIVE",
         "effective_at": "2025-03-05", "symbols": ["BBB"], "event_type": "LEGAL",
         "counterfactuals": [
             {"kind": "sign_flip", "text": "the co won", "direction": "POSITIVE"},
             {"kind": "escalation", "text": "the co was sued twice",
              "direction": "POSITIVE"}]},        # points the other way: dropped
        {"uid": "u3", "status": "REFUSED_SCHEMA", "anon": "junk", "direction": "POSITIVE",
         "counterfactuals": [{"kind": "sign_flip", "text": "x", "direction": "NEGATIVE"}]},
    ]


def test_only_ok_rows_reach_the_pairing(tmp_path):
    p = tmp_path / "c1.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _c1_rows()), encoding="utf-8")
    rows = be.load_c1(p)
    assert [r["uid"] for r in rows] == ["u1", "u2"], "a REFUSED_SCHEMA row is not data"


def test_the_pairing_keeps_only_defined_denominators_and_counts_the_rest():
    rows = [r for r in _c1_rows() if r["status"] == "OK"]
    pairs = be.pairs(rows)
    kinds = sorted((p["uid"], p["kind"]) for p in pairs)
    assert kinds == [("u1", "escalation"), ("u1", "sign_flip"), ("u2", "sign_flip")]
    drops = be.drop_reasons(rows)
    assert drops["escalation"]["escalation_points_the_other_way"] == 1
    assert drops["sign_flip"]["kept"] == 2


def test_the_placebo_pairs_a_headline_with_someone_elses_counterfactual():
    rows = [{"uid": f"u{i}", "status": "OK", "anon": f"real {i}", "direction": "POSITIVE",
             "effective_at": "2025-03-04", "symbols": [f"S{i}"], "event_type": "E",
             "counterfactuals": [{"kind": "sign_flip", "text": f"cf {i}",
                                  "direction": "NEGATIVE"}]}
            for i in range(12)]
    pairs = be.pairs(rows)
    placebo = be.placebo_pairs(pairs, seed=be.SEED)
    assert placebo, "a placebo leg must exist"
    for p in placebo:
        assert p["donor_uid"] != p["uid"], "a placebo paired with itself is not a placebo"
        assert p["cf_text"] != f"cf {p['uid'][1:]}"
    again = be.placebo_pairs(pairs, seed=be.SEED)
    assert [p["donor_uid"] for p in placebo] == [p["donor_uid"] for p in again]


# ------------------------------------------------------ the planted mechanism

def _answer_map(pairs, *, responsive: bool, rng):
    """A stubbed model. `responsive=True` reads the text and moves with it;
    `responsive=False` answers the same thing whatever it is shown."""
    out = {}
    for p in pairs:
        out[p["real_text"]] = (be.signed(p["parent_direction"]) or 1, 0.6)
        if responsive:
            out[p["cf_text"]] = (be.signed(p["cf_direction"]) or 1, 0.6)
        else:
            out[p["cf_text"]] = (1, 0.6)
    return out


def test_a_responsive_model_shows_elasticity_and_its_placebo_does_not():
    """The planted case: the model moves with the text. The TRUE pairs carry a
    positive elasticity of a known size; the placebo, where the counterfactual
    belongs to a different headline, must sit near zero once the denominators
    no longer line up."""
    rows = []
    for i in range(40):
        d = "POSITIVE" if i % 2 == 0 else "NEGATIVE"
        opp = "NEGATIVE" if d == "POSITIVE" else "POSITIVE"
        rows.append({"uid": f"u{i}", "status": "OK", "anon": f"real {i} {d}",
                     "direction": d, "effective_at": "2025-03-04",
                     "symbols": [f"S{i}"], "event_type": "E",
                     "counterfactuals": [{"kind": "sign_flip", "text": f"cf {i} {opp}",
                                          "direction": opp}]})
    pairs = be.pairs(rows)
    placebo = be.placebo_pairs(pairs, seed=be.SEED)
    answers = _answer_map(pairs + placebo, responsive=True,
                          rng=np.random.default_rng(1))
    scored = X2.score_pairs(pairs, answers)
    placebo_scored = X2.score_pairs(placebo, answers)
    s = X2.summarise(scored, placebo_scored)
    # every true pair: p_real = +/-0.6, p_cf = -/+0.6, delta = -/+2 -> 0.6 exactly
    assert s["elasticity_sign_flip"]["mean"] == pytest.approx(0.6)
    assert s["flip_test_pass_rate"] == 1.0
    assert abs(s["elasticity_placebo"]["mean"]) < abs(s["elasticity_sign_flip"]["mean"])
    assert s["paired_t_true_vs_placebo"]["n_uids"] >= 6


def test_an_unresponsive_model_shows_a_flip_rate_at_the_floor():
    rows = [{"uid": f"u{i}", "status": "OK", "anon": f"real {i}",
             "direction": "POSITIVE", "effective_at": "2025-03-04",
             "symbols": [f"S{i}"], "event_type": "E",
             "counterfactuals": [{"kind": "sign_flip", "text": f"cf {i}",
                                  "direction": "NEGATIVE"}]} for i in range(20)]
    pairs = be.pairs(rows)
    answers = _answer_map(pairs, responsive=False, rng=np.random.default_rng(2))
    scored = X2.score_pairs(pairs, answers)
    s = X2.summarise(scored, [])
    assert s["flip_test_pass_rate"] == 0.0, "the model never moved; nothing may pass"
    assert s["elasticity_sign_flip"]["mean"] == 0.0


def test_the_placebo_is_the_null_not_zero():
    """A summary that compared the true elasticity against 0 rather than
    against its own placebo would be the 2026-09-08 D1 mistake again."""
    assert "never zero" in X2.summarise([], [])["reading"]


# ------------------------------------------------------------ the feature table

def test_the_feature_table_keeps_the_three_legs_apart(tmp_path):
    scored = [
        {"uid": "u1", "kind": "sign_flip", "elasticity": 0.6, "flip_pass": 1,
         "symbols": ["AAA"], "effective_at": "2025-03-04", "event_type": "E"},
        {"uid": "u1", "kind": "escalation", "elasticity": 0.2, "flip_pass": 1,
         "symbols": ["AAA"], "effective_at": "2025-03-04", "event_type": "E"},
    ]
    placebo = [{"uid": "u1", "kind": "sign_flip", "elasticity": 0.01}]
    rows = be.feature_rows(scored, placebo)
    assert len(rows) == 1
    r = rows[0]
    assert r["belief_elasticity_sign_flip"] == 0.6
    assert r["belief_elasticity_escalation"] == 0.2
    assert r["belief_elasticity_placebo_null"] == 0.01
    out = be.write_feature_table(rows, run_date="2026-09-12", run=9, directory=tmp_path)
    assert out["rows"] == 1
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    entry = manifest["elasticity_2026-09-12_run09.parquet"]
    assert entry["rows"] == 1 and entry["sha256"] == out["sha256"]
    assert "fillna(0)" in entry["consumer"], "the no-fillna rule travels with the table"


def test_a_uid_with_no_placebo_carries_none_not_zero():
    rows = be.feature_rows([{"uid": "u1", "kind": "sign_flip", "elasticity": 0.6,
                             "flip_pass": 1, "symbols": [], "effective_at": None,
                             "event_type": None}], [])
    assert rows[0]["belief_elasticity_placebo_null"] is None


def test_the_parquet_is_gitignored_and_the_manifest_is_not():
    """The 2026-09-11 CI red was the opposite arrangement."""
    from pathlib import Path

    ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
    assert "backend/data/optimus/x_lane/*.parquet" in ignore
    assert "backend/data/optimus/x_lane/MANIFEST.json" not in ignore


def test_the_pit_rule_is_stated_for_the_receipt():
    note = be.pit_note()
    assert "effective_at" in note and "no future information" in note


# ------------------------------------------------------------------- the job

def test_the_job_refuses_by_name_when_the_reader_is_down(monkeypatch, tmp_path):
    monkeypatch.setattr(X2, "OUT", tmp_path)
    monkeypatch.setattr(X2, "_probe", lambda backend: "ProviderRefusal: local unreachable")
    monkeypatch.setattr(be, "load_c1",
                        lambda path=None: [r for r in _c1_rows() if r["status"] == "OK"])
    payload = X2.X2_elasticity(max_cells=3, run=7)
    assert payload["verdict"].startswith("PENDING_MODEL")
    assert (tmp_path / "X2_elasticity_run07_cells.json").is_file()
    assert pp.refuse_reasons("X2_elasticity", payload) == []
    assert payload["full_pass_projection"]["projected_serial_wall_time_hours"] == "36-43"
    assert payload["construction"]["per_kind"]["escalation"][
        "escalation_points_the_other_way"] == 1


def test_a_full_run_with_a_mocked_reader_writes_a_feature_table(monkeypatch, tmp_path):
    from types import SimpleNamespace

    rows = []
    for i in range(24):
        d = "POSITIVE" if i % 2 == 0 else "NEGATIVE"
        opp = "NEGATIVE" if d == "POSITIVE" else "POSITIVE"
        rows.append({"uid": f"u{i}", "status": "OK", "anon": f"real {i} up",
                     "direction": d, "effective_at": "2025-03-04",
                     "symbols": [f"S{i}"], "event_type": "E",
                     "counterfactuals": [{"kind": "sign_flip", "text": f"cf {i} down",
                                          "direction": opp}]})
    monkeypatch.setattr(X2, "OUT", tmp_path)
    monkeypatch.setattr(be, "FEATURE_DIR", tmp_path / "x_lane")
    monkeypatch.setattr(X2, "_probe", lambda backend: None)
    monkeypatch.setattr(be, "load_c1", lambda path=None: rows)

    import backend.services.free_inference as fi

    def fake(backend, prompt, **kw):
        assert kw.get("purpose") == "x2_belief_elasticity"
        d = "DOWN" if " down" in prompt else "UP"
        return SimpleNamespace(text=f"DIRECTION: {d}\nCONFIDENCE: 0.6",
                               tokens_in=80, tokens_out=8)

    monkeypatch.setattr(fi, "complete", fake)
    payload = X2.X2_elasticity(run=8)
    assert payload["n_pairs_scored"] == 24
    assert pp.refuse_reasons("X2_elasticity", payload) == []
    assert payload["P1_P6"]["P3_direction_flip"]["n"] > 0
    table = payload["feature_table"]
    assert table["rows"] == 24
    from pathlib import Path

    assert Path(table["path"]).is_file()


def test_the_job_is_registered_and_never_starts_the_model_server():
    import ast
    from pathlib import Path

    from scripts import night_factory_jobs as NFJ

    assert "X2_elasticity" in NFJ.JOBS
    for mod in (X2.__file__, be.__file__):
        for node in ast.walk(ast.parse(Path(mod).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in {"start", "stop",
                                                                 "bind_lifetime"}:
                holder = getattr(node.value, "id", None) or getattr(node.value, "attr", None)
                assert holder not in ("llama_server", "ls")
