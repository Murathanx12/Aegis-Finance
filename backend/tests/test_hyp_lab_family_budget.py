"""D6 / CHUNK C12 (2026-10-06), as amended by the adversarial review
(docs/reviews/REVIEW_2026-10-06_C12_THEORY_CELLS.md): hyp_lab feeds each family's Beta posterior
BACKWARD into generation and ranking, as two policy_state PREFERENCES.

Pinned here:
* a family at posterior 0.10 is offered, and admits, fewer new hypotheses than one at 0.40;
* the shrink is never a kill: quota >= 1, weight >= its floor, nothing deleted, over-quota rows
  DEFERRED and re-admitted when the family recovers -- including after failures + one positive;
* the posterior counts only POWERED negatives (CANNOT_DISTINGUISH 0, unpowered FAILED 0),
  a re-read of a library rule counts +0, and verdicts older than 180 days count half;
* a free-text family label is UNMAPPED and gets the median quota, never a fresh full one;
* the prompt never names shrunk families or their caps;
* the generation quota and the EV weight are both declared policy_state keys;
* a shrunk family not run in a week gets a guaranteed slot;
* the dollar caps are untouched.

Offline, synthetic rows; no LLM call (the generation path runs on a stub).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import config as C
from backend.services import hyp_lab as L
from backend.services import policy_state as PS

TEST_FAMILIES = ("weak", "strong", "fam", "f", "g", "weak_family", "other_family", "fam_a", "fam_b")


@pytest.fixture(autouse=True)
def taxonomy(monkeypatch):
    monkeypatch.setattr(C, "HYP_LAB_FAMILIES", tuple(C.HYP_LAB_FAMILIES) + TEST_FAMILIES)


def _h(family: str, i: int, **kw) -> dict:
    base = dict(title=f"{family} idea {i}", mechanism=f"mechanism text for {family} number {i}",
                precursor="an observable known before the trade at close t",
                separation_from_beta="matched control printed apart",
                refutation="confirm-fold mean at or below zero", target="return", family=family,
                source="test", cell_type="macro_lead_lag",
                params={"driver": "CL=F", "targets": ["AAA", "BBB"], "expected_sign": 1, "h": 1, "i": i})
    base.update(kw)
    return L.make_hypothesis(**base)


POWERED = {"powered": True, "confirm": {"mean": -0.01, "t": -3.0, "mde": 0.002}}
UNPOWERED = {"confirm": {"mean": -0.001, "t": -0.4, "mde": 0.02}, "design": {"mean": 0.001}}


def _ran(family: str, i: int, verdict: str, summary: dict | None = None, utc: str | None = None, **kw) -> dict:
    h = _h(family, 100 + i)
    return {**h, "hyp_id": f"{family}-{verdict}-{i}", "status": "RUN", "verdict": verdict,
            "last_summary": summary if summary is not None else POWERED,
            "history": [{"status": "RUN", "verdict": verdict, "utc": utc or L.now_utc()}], **kw}


def _fails(family: str, n: int, **kw) -> dict:
    return {r["hyp_id"]: r for r in (_ran(family, i, "FAILED_VARIANT", **kw) for i in range(n))}


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
    """The brief's pin: posterior 0.10 generates fewer than posterior 0.40 -- in the budget AND in
    what one generation round admits."""
    budget = L.family_budget({"weak": _fam(0.10), "strong": _fam(0.40)}, n=8)
    assert budget["weak"]["quota"] < budget["strong"]["quota"]
    assert budget["weak"]["quota"] >= 1, "a shrink, never a kill"
    rows = [_h("weak", i) for i in range(5)] + [_h("strong", i) for i in range(5)]
    out = L.apply_family_budget(rows, budget, n=8)
    admitted = lambda f: sum(1 for r in out if r["family"] == f and r["status"] == "PROPOSED")  # noqa: E731
    assert admitted("weak") < admitted("strong")
    assert admitted("weak") == budget["weak"]["quota"]
    assert len(out) == len(rows), "nothing is dropped: over-quota rows are kept, DEFERRED"
    deferred = [r for r in out if r["status"] == "DEFERRED_FAMILY_BUDGET"]
    assert deferred and all(r["deferred_from_status"] == "PROPOSED" and r["deferred_reason"] for r in deferred)


def test_unmapped_family_gets_the_median_quota_not_a_fresh_full_one():
    """Review F7: renaming must not buy a fresh full quota."""
    assert L.canonical_family("brand_new_label") == C.HYP_LAB_UNMAPPED_FAMILY
    assert L.canonical_family("insider_hold") == "insider_event", "a known split folds into its family"
    fam = {"weak": _fam(0.05), "fam": _fam(0.10), "strong": _fam(0.40)}
    b = L.family_budget(fam, n=8)
    quotas = sorted(b[f]["quota"] for f in fam)
    assert b[C.HYP_LAB_UNMAPPED_FAMILY]["quota"] == quotas[1] < b["strong"]["quota"]
    rows = [_h("brand_new_label", i) for i in range(4)]
    rows = [{**r, "family": L.canonical_family(r["family"])} for r in rows]
    out = L.apply_family_budget(rows, b, n=8)
    assert sum(r["status"] == "PROPOSED" for r in out) == quotas[1]


def test_parse_generated_files_free_text_labels_as_unmapped(monkeypatch):
    from backend.services import hyp_cells as HC
    monkeypatch.setattr(HC, "bar_symbols", lambda: frozenset({"AAA", "BBB"}))
    items = [{"title": "x", "mechanism": "a mechanism long enough to count", "precursor": "observable at close t ok",
              "separation_from_beta": "control", "refutation": "confirm mean at or below zero", "target": "return",
              "family": "Totally New Family", "cell_type": None, "params": {}}]
    row = L.parse_generated(items, "stub", "ref")[0]
    assert row["family"] == C.HYP_LAB_UNMAPPED_FAMILY and row["family_label"] == "totally_new_family"


def test_posterior_counts_only_powered_negatives():
    """Review F6: CANNOT_DISTINGUISH is 0, an unpowered FAILED_VARIANT is 0, a powered one is 1."""
    prior = L.FAMILY_PRIOR[0] / sum(L.FAMILY_PRIOR)
    unpowered = {**_fails("fam", 4, summary=UNPOWERED),
                 **{r["hyp_id"]: r for r in (_ran("fam", 10 + i, "CANNOT_DISTINGUISH", summary=UNPOWERED)
                                             for i in range(4))}}
    assert L.family_record(unpowered)["fam"]["p_positive"] == pytest.approx(prior, abs=1e-4)
    powered = _fails("fam", 4)
    p4 = L.family_record(powered)["fam"]["p_positive"]
    assert p4 == pytest.approx(1 / (1 + 4 + 4), abs=1e-4)
    # explicit flag wins over the inference
    flagged = _fails("fam", 2, summary={**UNPOWERED, "powered": True})
    assert L.family_record(flagged)["fam"]["failed_powered"] == 2


def test_old_verdicts_count_half():
    old = (datetime.now(timezone.utc) - timedelta(days=C.HYP_LAB_VERDICT_DECAY_DAYS + 5)).isoformat()
    r = L.family_record(_fails("fam", 4, utc=old))["fam"]
    assert r["failed_powered"] == pytest.approx(2.0)


def test_reread_of_a_library_rule_counts_zero(tmp_path):
    """Review F8: a cell that re-reads a rule already run on CRSP is +0, as the prose said."""
    (tmp_path / "library_rules_LIB_X.jsonl").write_text(
        json.dumps({"rule": "hi52", "status": "RUN", "headline": "FAILED_VARIANT"}) + "\n"
        + json.dumps({"rule": "roe", "status": "RUN"}) + "\n", encoding="utf-8")
    rules = L.library_rules(tmp_path)
    assert set(rules) == {"hi52"}, "plain-word rule names are left to the cosine check"
    row = _h("fam", 1, precursor="price / 52-week high at month end (strategy_library rule hi52)")
    assert L.reread_of(row, rules) and L.reread_of(_h("fam", 2), rules) is None
    out = L.dedupe([row], {}, corpus=[], rules=rules)[0]
    assert out["status"] == "DUPLICATE_OF_CLOSED" and out["reread_of"].endswith("#hi52")
    declared = L.dedupe([{**row, "declared_reread": True}], {}, corpus=[], rules=rules)[0]
    assert declared["status"] == "PROPOSED" and declared["reread_of"]
    state = {"R": {**declared, "hyp_id": "R", "status": "RUN", "verdict": "FAILED_VARIANT",
                   "last_summary": POWERED, "history": [{"status": "RUN", "verdict": "FAILED_VARIANT", "utc": L.now_utc()}]}}
    rec = L.family_record(state)["fam"]
    assert rec["failed_powered"] == 0 and rec["rereads"] == 1
    assert rec["p_positive"] == pytest.approx(L.FAMILY_PRIOR[0] / sum(L.FAMILY_PRIOR), abs=1e-4)


def test_ev_is_shrunk_in_ranking_not_deleted():
    rows = [_h("weak", 1), _h("strong", 1)]
    state = {r["hyp_id"]: {**r, "history": []} for r in rows}
    w = L.ev_weights_from_budget(L.family_budget({"weak": _fam(0.10), "strong": _fam(0.40)}, 8))
    assert set(w) == {"weak"}, "only shrunk families carry an EV preference"
    q = L.rank(state, runnable_only=True, ev_weights=w)
    assert [h["family"] for h in q] == ["strong", "weak"], "both still ranked; the weak one lower"
    weak = next(h for h in q if h["family"] == "weak")["score"]
    assert weak["ev_weight"] == pytest.approx(w["weak"]) and weak["ev"] < weak["ev_unshrunk"]


def test_deferred_rows_return_after_failures_then_one_positive():
    """Review F6: recovery from a real shrink, not from an empty record."""
    deferred = L.apply_family_budget([_h("fam", 1), _h("fam", 2)],
                                     {"fam": {"quota": 1, "p_positive": 0.05}}, n=8)[1]
    assert deferred["status"] == "DEFERRED_FAMILY_BUDGET"
    state = {deferred["hyp_id"]: {**deferred, "history": []}, **_fails("fam", 4)}
    assert L.family_record(state)["fam"]["p_positive"] < C.HYP_LAB_FAMILY_POSTERIOR_FLOOR
    assert deferred["hyp_id"] not in {h["hyp_id"] for h in L.rank(state, ev_weights={})}
    pos = _ran("fam", 50, "CANDIDATE")
    state[pos["hyp_id"]] = pos
    assert L.family_record(state)["fam"]["p_positive"] >= C.HYP_LAB_FAMILY_POSTERIOR_FLOOR
    q = L.rank(state, ev_weights={})
    assert deferred["hyp_id"] in {h["hyp_id"] for h in q}


def test_weekly_guarantee_runs_a_shrunk_family():
    deferred = L.apply_family_budget([_h("fam", 1), _h("fam", 2)],
                                     {"fam": {"quota": 1, "p_positive": 0.05}}, n=8)[1]
    old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    state = {deferred["hyp_id"]: {**deferred, "history": []}, **_fails("fam", 4, utc=old)}
    g = L.weekly_guarantee(state, {"fam": 0.5})
    assert [x["hyp_id"] for x in g] == [deferred["hyp_id"]] and g[0]["guaranteed"]
    recent = {deferred["hyp_id"]: {**deferred, "history": []}, **_fails("fam", 4)}
    assert L.weekly_guarantee(recent, {"fam": 0.5}) == [], "run this week: no guarantee needed"
    assert L.weekly_guarantee(state, {"fam": 1.0}) == [], "an unshrunk family needs none"


def test_generation_prompt_never_names_shrunk_families_or_caps():
    state = {**_fails("weak_family", 4), "S": {**_h("other_family", 1), "hyp_id": "S", "history": []}}
    budget = L.family_budget(L.family_record(state), 8)
    assert budget["weak_family"]["shrunk"] and not budget["other_family"]["shrunk"]
    prompt = L.generation_prompt(state, L.CELL_CATALOG, n=8)
    assert "at most" not in prompt and "FAMILY BUDGET" not in prompt
    assert "FAMILY LABELS" in prompt and C.HYP_LAB_UNMAPPED_FAMILY in prompt


def test_candidate_verdict_counts_as_a_positive():
    rows = {"A": _ran("f", 1, "CANDIDATE"), "B": _ran("g", 1, "FAILED_VARIANT")}
    fam = L.family_record(rows)
    assert fam["f"]["CONDITIONAL_POSITIVE"] == 1 and fam["f"]["p_positive"] > fam["g"]["p_positive"]


def test_policy_state_keys_are_declared_bounded_and_refuse_a_kill(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    with pytest.raises(PS.PolicyRefused):
        PS.update("hyp_family_ev_weight", {"weak": 0.0}, reason="kill it", evidence={"n": 1})
    with pytest.raises(PS.PolicyRefused):
        PS.update("hyp_family_gen_quota", {"weak": 0}, reason="kill it", evidence={"n": 1})
    PS.update("hyp_family_ev_weight", {"weak": 0.6667}, reason="D6", evidence={"posterior": 0.10})
    PS.update("hyp_family_gen_quota", {"weak": 2}, reason="D6", evidence={"posterior": 0.10})
    assert L.policy_ev_weights() == {"weak": 0.6667} and L.policy_gen_quotas() == {"weak": 2}
    b = L.family_budget({"weak": _fam(0.40)}, 8, quotas=L.policy_gen_quotas())
    assert b["weak"]["quota"] == 2 and b["weak"]["quota_source"] == "policy_state"


def test_nightly_family_policy_writes_both_preferences_and_reports(tmp_path, monkeypatch):
    from scripts import hyp_lab as S
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    queued = {"Q": {**_h("weak_family", 99), "hyp_id": "Q", "history": []}}
    state = {**_fails("weak_family", 4), **queued}
    rep = S.family_policy(state, 8, apply=True, generated=[_h("weak_family", 50)])
    assert rep["policy_state"].startswith("WRITTEN") and "hyp_family_gen_quota" in rep["policy_state"]
    f = rep["families"]["weak_family"]
    assert f["posterior"] < C.HYP_LAB_FAMILY_POSTERIOR_FLOOR and f["n_shrunk"] == 1 and f["n_generated_tonight"] == 1
    vals = json.loads((tmp_path / "policy_state.json").read_text(encoding="utf-8"))["values"]
    assert vals["hyp_family_ev_weight"] == rep["ev_weights"] and vals["hyp_family_gen_quota"] == rep["gen_quotas"]
    assert S.family_policy(state, 8, apply=True)["policy_state"] == "UNCHANGED"


def test_generate_applies_the_budget_without_a_paid_call(tmp_path, monkeypatch):
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
    monkeypatch.setattr(L, "dedupe", lambda rows, state, corpus=None, rules=None: rows)
    from backend.services import hyp_cells as HC
    monkeypatch.setattr(HC, "bar_symbols", lambda: frozenset({"AAA", "BBB"}))
    budget = {"weak": {"p_positive": 0.10, "weight": 0.6667, "quota": 2, "shrunk": True}}
    g = S.generate("deepseek", 8, cap=0.40, budget=budget)
    assert seen["cap"] == 0.40, "the run cap reaches the paid path unchanged"
    assert "at most" not in seen["user"]
    st = [r["status"] for r in g["rows"]]
    assert st.count("NEEDS_CELL") == 2 and st.count("DEFERRED_FAMILY_BUDGET") == 3
    assert len(L.load_state()) == 5, "every generated row is in the ledger"


def test_dollar_caps_are_untouched():
    assert C.HYP_LAB_NIGHT_CAP_USD == 3.00
    assert C.HYP_LAB_NIGHTLY_CAP_USD == 0.40
