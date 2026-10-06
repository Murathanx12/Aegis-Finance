"""D6 / CHUNK C12 (2026-10-06): hyp_lab feeds each family's Beta posterior BACKWARD into
generation (borrowed from RD-Agent(Q)'s bandit scheduler) and shrinks its EV in ranking as a
policy_state PREFERENCE.

Pinned here:
* a family at posterior 0.10 is offered, and admits, fewer new hypotheses than one at 0.40;
* the shrink is a shrink, never a kill: every quota >= 1, the weight never under its floor,
  nothing is deleted from the ledger, over-quota rows are DEFERRED (not closed) and come back
  when the family's posterior recovers;
* the EV weight comes from the declared policy_state key, which refuses a zero;
* the generation prompt names the shrunk families;
* the dollar caps are untouched.

Offline, synthetic rows only; no LLM call is made (the generation path is exercised with a stub).
"""
from __future__ import annotations

import json

import pytest

from backend import config as C
from backend.services import hyp_lab as L
from backend.services import policy_state as PS


def _h(family: str, i: int, **kw) -> dict:
    base = dict(title=f"{family} idea {i}", mechanism=f"mechanism text for {family} number {i}",
                precursor="an observable known before the trade at close t",
                separation_from_beta="matched control printed apart",
                refutation="confirm-fold mean at or below zero", target="return", family=family,
                source="test", cell_type="macro_lead_lag",
                params={"driver": "CL=F", "targets": ["AAA", "BBB"], "expected_sign": 1, "h": 1, "i": i})
    base.update(kw)
    return L.make_hypothesis(**base)


def _fam(p: float) -> dict:
    return {"CONDITIONAL_POSITIVE": 0, "FAILED_VARIANT": 0, "CANNOT_DISTINGUISH": 0, "REFUSED": 0,
            "n_rows": 5, "p_positive": p}


def test_weight_is_one_above_floor_proportional_below_and_never_zero():
    floor = C.HYP_LAB_FAMILY_POSTERIOR_FLOOR
    assert L.family_weight(0.40) == 1.0
    assert L.family_weight(floor) == 1.0
    assert L.family_weight(0.10) == pytest.approx(0.10 / floor, abs=1e-4)
    assert L.family_weight(0.0) == C.HYP_LAB_FAMILY_MIN_WEIGHT > 0


def test_low_posterior_family_generates_fewer_than_a_healthy_one():
    """The brief's pin: posterior 0.10 generates fewer than posterior 0.40 -- in the budget the
    prompt carries AND in what one generation round admits."""
    budget = L.family_budget({"weak": _fam(0.10), "strong": _fam(0.40)}, n=8)
    assert budget["weak"]["quota"] < budget["strong"]["quota"]
    assert budget["weak"]["quota"] >= 1, "a shrink, never a kill"
    # one round where the model ignores the budget and proposes 5 of each
    rows = [_h("weak", i) for i in range(5)] + [_h("strong", i) for i in range(5)]
    out = L.apply_family_budget(rows, budget, n=8)
    admitted = lambda f: sum(1 for r in out if r["family"] == f and r["status"] == "PROPOSED")  # noqa: E731
    assert admitted("weak") < admitted("strong")
    assert admitted("weak") == budget["weak"]["quota"]
    assert len(out) == len(rows), "nothing is dropped: over-quota rows are kept, DEFERRED"
    assert {r["status"] for r in out} <= {"PROPOSED", "DEFERRED_FAMILY_BUDGET"}
    deferred = [r for r in out if r["status"] == "DEFERRED_FAMILY_BUDGET"]
    assert all(r["deferred_from_status"] == "PROPOSED" and r["deferred_reason"] for r in deferred)


def test_ev_is_shrunk_in_ranking_not_deleted(tmp_path):
    rows = [_h("weak", 1), _h("strong", 1)]
    state = {r["hyp_id"]: {**r, "history": []} for r in rows}
    w = L.ev_weights_from_budget(L.family_budget({"weak": _fam(0.10), "strong": _fam(0.40)}, 8))
    assert set(w) == {"weak"}, "only shrunk families carry a preference"
    q = L.rank(state, runnable_only=True, ev_weights=w)
    assert [h["family"] for h in q] == ["strong", "weak"], "both still ranked; the weak one lower"
    weak = next(h for h in q if h["family"] == "weak")["score"]
    assert weak["ev_weight"] == pytest.approx(w["weak"])
    assert weak["ev"] < weak["ev_unshrunk"]
    assert len(L.rank(state, ev_weights={})) == 2


def test_deferred_rows_return_when_the_family_recovers():
    deferred = L.apply_family_budget([_h("fam", 1), _h("fam", 2)],
                                     {"fam": {"quota": 1, "p_positive": 0.05}}, n=8)[1]
    assert deferred["status"] == "DEFERRED_FAMILY_BUDGET"
    state = {deferred["hyp_id"]: {**deferred, "history": []}}
    # the family's only row is the deferred one: prior Beta(1,4) -> posterior 0.2 >= floor -> re-admitted
    q = L.rank(state, ev_weights={})
    assert [h["hyp_id"] for h in q] == [deferred["hyp_id"]] and q[0]["status"] == "PROPOSED"
    # a family that keeps failing keeps it deferred (still in the ledger, not in the queue)
    fails = {f"F{i}": {**_h("fam", 10 + i), "hyp_id": f"F{i}", "status": "RUN", "verdict": "FAILED_VARIANT",
                       "history": []} for i in range(4)}
    assert deferred["hyp_id"] not in {h["hyp_id"] for h in L.rank({**state, **fails}, ev_weights={})}


def test_generation_prompt_names_the_shrunk_family_and_its_quota():
    weak = {f"W{i}": {**_h("weak_family", i), "hyp_id": f"W{i}", "status": "RUN", "verdict": "FAILED_VARIANT",
                      "history": []} for i in range(4)}
    state = {**weak, "S": {**_h("other_family", 1), "hyp_id": "S", "history": []}}
    budget = L.family_budget(L.family_record(state), 8)
    assert budget["weak_family"]["shrunk"] and not budget["other_family"]["shrunk"]
    prompt = L.generation_prompt(state, L.CELL_CATALOG, n=8)
    assert "FAMILY BUDGET" in prompt
    assert f"weak_family: at most {budget['weak_family']['quota']} of 8" in prompt
    assert "other_family: at most" not in prompt


def test_candidate_verdict_counts_as_a_positive():
    rows = {"A": {**_h("f", 1), "hyp_id": "A", "verdict": "CANDIDATE", "history": []},
            "B": {**_h("g", 1), "hyp_id": "B", "verdict": "FAILED_VARIANT", "history": []}}
    fam = L.family_record(rows)
    assert fam["f"]["CONDITIONAL_POSITIVE"] == 1 and fam["f"]["p_positive"] > fam["g"]["p_positive"]


def test_policy_state_key_is_declared_bounded_and_refuses_a_kill(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    assert "hyp_family_ev_weight" in PS.SCHEMA
    with pytest.raises(PS.PolicyRefused):
        PS.update("hyp_family_ev_weight", {"weak": 0.0}, reason="kill it", evidence={"n": 1})
    PS.update("hyp_family_ev_weight", {"weak": 0.6667}, reason="D6", evidence={"posterior": 0.10})
    assert L.policy_ev_weights() == {"weak": 0.6667}
    assert len((tmp_path / "policy_journal.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_nightly_family_policy_writes_preference_and_reports_per_family(tmp_path, monkeypatch):
    from scripts import hyp_lab as S
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    weak = {f"W{i}": {**_h("weak_family", i), "hyp_id": f"W{i}", "status": "RUN", "verdict": "FAILED_VARIANT",
                      "history": []} for i in range(4)}
    queued = {"Q": {**_h("weak_family", 99), "hyp_id": "Q", "history": []}}
    rep = S.family_policy({**weak, **queued}, 8, apply=True, generated=[_h("weak_family", 50)])
    assert rep["policy_state"] == "WRITTEN"
    f = rep["families"]["weak_family"]
    assert set(f) >= {"posterior", "n_generated_tonight", "n_shrunk"}
    assert f["posterior"] < C.HYP_LAB_FAMILY_POSTERIOR_FLOOR and f["n_shrunk"] == 1 and f["n_generated_tonight"] == 1
    assert json.loads((tmp_path / "policy_state.json").read_text(encoding="utf-8"))["values"][
        "hyp_family_ev_weight"] == rep["ev_weights"]
    again = S.family_policy({**weak, **queued}, 8, apply=True)
    assert again["policy_state"] == "UNCHANGED"


def test_generate_applies_the_budget_without_a_paid_call(tmp_path, monkeypatch):
    """The generation path, with the LLM stubbed: the low family's extra rows are DEFERRED, and
    the run's dollar cap passed to the call is the caller's, untouched by the wiring."""
    from scripts import hyp_lab as S
    monkeypatch.setattr(L, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(L, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(L, "REPO", tmp_path)
    seen = {}

    def fake_call(system, user, **kw):
        seen["cap"], seen["user"] = kw.get("cap_usd"), user
        items = [{"title": f"weak {i}", "mechanism": f"weak mechanism {i} long enough text", "precursor":
                  "observable at close t before trading", "separation_from_beta": "control",
                  "refutation": "confirm mean at or below zero", "target": "return", "family": "weak",
                  "cell_type": None, "params": {}} for i in range(5)]
        return {"ok": True, "status": "OK", "text": json.dumps(items), "served_model": "stub"}

    monkeypatch.setattr(S.HL, "call", fake_call)
    monkeypatch.setattr(L, "dedupe", lambda rows, state, corpus=None: rows)
    from backend.services import hyp_cells as HC
    monkeypatch.setattr(HC, "bar_symbols", lambda: frozenset({"AAA", "BBB"}))
    budget = {"weak": {"p_positive": 0.10, "weight": 0.6667, "quota": 2, "shrunk": True}}
    g = S.generate("deepseek", 8, cap=0.40, budget=budget)
    assert seen["cap"] == 0.40, "the run cap reaches the paid path unchanged"
    assert "weak: at most 2 of 8" in seen["user"]
    st = [r["status"] for r in g["rows"]]
    assert st.count("NEEDS_CELL") == 2 and st.count("DEFERRED_FAMILY_BUDGET") == 3
    assert len(L.load_state()) == 5, "every generated row is in the ledger"


def test_dollar_caps_are_untouched():
    assert C.HYP_LAB_NIGHT_CAP_USD == 3.00
    assert C.HYP_LAB_NIGHTLY_CAP_USD == 0.40
