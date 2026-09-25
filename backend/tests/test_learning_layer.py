"""The learning layer (adjudication 2026-09-26 row 9): the distillation writes
rules or says why, and `policy_state.json` exists and moves only from grades.

Offline: every model call and every spend read is a stub.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from backend.services import forecast_reputation as FR
from backend.services import ledger_retrieval as LR
from backend.services import policy_state as PS
from learner import rule_distillation as RD

AS_OF = "2026-09-26"


def _rows(n: int = 80, *, specialist: str = "investigator:A_snapshot",
          observable: str = "abs_move_exceeds", horizon: int = 1,
          resolved_at: str = "2026-09-20", skilled: bool = True,
          seed: int = 3) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    start = date(2026, 8, 11)
    for i in range(n):
        y = int(rng.random() < 0.3)
        p = (0.6 if y else 0.15) if skilled else float(rng.uniform(0.2, 0.4))
        out.append({
            "prediction_id": f"{specialist}-{observable}-{i}",
            "ticker": f"T{i % 7}", "specialist": specialist,
            "observable": observable, "horizon_days": horizon,
            "probability": p, "outcome": y, "void_reason": None,
            "made_at": f"{start + timedelta(days=i % 8)}T12:00:00+00:00",
            "resolved_at": resolved_at,
        })
    return out


def _ledger() -> list[dict]:
    return (_rows() + _rows(specialist="macro_rates", skilled=False, seed=4)
            + _rows(specialist="skeptic", skilled=False, seed=5))


def _reply_for(prompt: str) -> str:
    """A well-formed reply citing every fact, quoting the fact's own skill."""
    import re
    rules = []
    for line in prompt.splitlines():
        if line.startswith("F") and " | " in line:
            fid = line.split(" | ")[0]
            num = re.search(r"(?:climatology|gap) ([+-]\d+\.\d+%)", line).group(1)
            verdict = line.rsplit("VERDICT ", 1)[1].strip()
            stance = "may be used" if verdict == "SKILL" else "weight 0"
            rules.append({"fact": fid, "rule": f"{fid} {stance}: skill {num}."})
    return json.dumps({"rules": rules})


def _paths(tmp_path: Path) -> dict:
    return {"rules_path": tmp_path / "learned_rules.jsonl",
            "runs_path": tmp_path / "learn_runs.jsonl", "md_dir": tmp_path}


def _refuse_local(prompt):
    raise ConnectionRefusedError("[WinError 10061] actively refused")


def _spend_zero(since):
    return {"n_calls": 0, "total_cost_usd": 0.0, "total_is_lower_bound": False}


# ─────────────────────────── inputs are hindsight-safe ──────────────────────

def test_only_rows_resolved_strictly_before_the_rule_date_are_read():
    rows = _rows(5) + _rows(5, resolved_at=AS_OF, seed=9)
    rows[0]["void_reason"] = "bad bar"
    rows[1]["outcome"] = None
    kept = RD.graded_rows_before(rows, AS_OF)
    assert len(kept) == 3
    assert all(r["resolved_at"] < AS_OF for r in kept)


def test_fact_numbers_are_the_reputation_convention_not_a_second_one():
    facts = RD.ledger_facts(_ledger(), as_of=AS_OF, min_n=30)
    inv = next(f for f in facts if f["fact_key"] == "class:investigator|abs_move_exceeds|h1")
    g = FR.graded_frame_from_rows(_rows()).sort_values("made_at", kind="stable")
    held = FR._score(g["p"].to_numpy(float)[40:], g["y"].to_numpy(float)[40:])
    assert inv["n"] == 80 and inv["n_heldout"] == 40
    assert inv["skill"] == pytest.approx(held["skill"], abs=1e-4)
    assert inv["made_from_dates"][0] == "2026-08-11" and inv["n_date_blocks"] == 8
    keys = {f["fact_key"] for f in facts}
    assert "class:personas|abs_move_exceeds|h1" in keys       # pooled personas
    assert "family:macro_rates|abs_move_exceeds|h1" in keys
    assert not any(k.startswith("family:investigator") for k in keys)


# ─────────────────────────── the distillation writes rules ─────────────────

def test_local_refusal_falls_back_to_deepseek_and_the_rule_carries_its_numbers(tmp_path):
    calls = []

    def remote(prompt):
        calls.append(prompt)
        return _reply_for(prompt), {"model": "deepseek/deepseek-chat"}

    rec = RD.distill_ledger(as_of=AS_OF, rows=_ledger(), reputation={},
                            reputation_path="rep.json", autopsy={}, autopsy_path="a.json",
                            local_fn=_refuse_local, remote_fn=remote,
                            spend_fn=_spend_zero, **_paths(tmp_path))
    assert rec["status"] == "LEARNED" and rec["n_rules_written"] >= 3
    assert rec["local_status"].startswith("REFUSED")
    assert rec["answered_by"] == "deepseek/deepseek-chat"
    rules = [json.loads(x) for x in
             (tmp_path / "learned_rules.jsonl").read_text(encoding="utf-8").splitlines()]
    r = next(x for x in rules if x["fact_key"] == "class:investigator|abs_move_exceeds|h1")
    for k in ("n", "brier", "skill", "made_from_dates", "rule_hash"):
        assert r[k] not in (None, [], "")
    assert r["hindsight_safe"] is True and r["resolution_date"] < AS_OF
    assert r["rule_hash"] == RD._hash_rule(r)
    md = (tmp_path / "LEARNED_2026-09.md").read_text(encoding="utf-8")
    assert "LEARNED" in md and r["rule_text"] in md
    assert "local REFUSED" in md or "REFUSED" in md


def test_the_local_model_is_used_when_it_answers(tmp_path):
    rec = RD.distill_ledger(
        as_of=AS_OF, rows=_ledger(), reputation={}, reputation_path=None,
        autopsy={}, autopsy_path=None,
        local_fn=lambda p: (_reply_for(p), {"model": "local_gguf/local"}),
        remote_fn=lambda p: pytest.fail("DeepSeek called although local answered"),
        spend_fn=_spend_zero, **_paths(tmp_path))
    assert rec["status"] == "LEARNED" and rec["answered_by"] == "local_gguf/local"
    assert rec["local_status"] == "ok"


def test_both_models_refusing_is_LEARN_DEGRADED_with_the_reason(tmp_path):
    rec = RD.distill_ledger(as_of=AS_OF, rows=_ledger(), reputation={},
                            reputation_path=None, autopsy={}, autopsy_path=None,
                            local_fn=_refuse_local,
                            remote_fn=lambda p: (None, {"model": "deepseek/x"}),
                            spend_fn=_spend_zero, **_paths(tmp_path))
    assert rec["status"] == "LEARN_DEGRADED"
    assert rec["reason"].startswith("model refused")
    assert not (tmp_path / "learned_rules.jsonl").exists()
    assert "LEARN_DEGRADED" in (tmp_path / "LEARNED_2026-09.md").read_text(encoding="utf-8")


def test_the_cap_stops_deepseek_and_says_cap(tmp_path):
    rec = RD.distill_ledger(
        as_of=AS_OF, rows=_ledger(), reputation={}, reputation_path=None,
        autopsy={}, autopsy_path=None, local_fn=_refuse_local,
        remote_fn=lambda p: pytest.fail("called past the cap"),
        spend_fn=lambda since: {"n_calls": 9, "total_cost_usd": 0.51},
        **_paths(tmp_path))
    assert rec["status"] == "LEARN_DEGRADED" and rec["reason"].startswith("cap")


def test_unknown_spend_is_the_cap_not_a_zero(tmp_path):
    rec = RD.distill_ledger(
        as_of=AS_OF, rows=_ledger(), reputation={}, reputation_path=None,
        autopsy={}, autopsy_path=None, local_fn=_refuse_local,
        remote_fn=lambda p: pytest.fail("called with spend unknown"),
        spend_fn=lambda since: {}, **_paths(tmp_path))
    assert rec["status"] == "LEARN_DEGRADED" and rec["reason"].startswith("cap")


def test_a_second_night_on_the_same_grades_is_no_new_graded_rows(tmp_path):
    kw = dict(as_of=AS_OF, rows=_ledger(), reputation={}, reputation_path=None,
              autopsy={}, autopsy_path=None, local_fn=_refuse_local,
              remote_fn=lambda p: (_reply_for(p), {"model": "deepseek/x"}),
              spend_fn=_spend_zero, **_paths(tmp_path))
    assert RD.distill_ledger(**kw)["status"] == "LEARNED"
    again = RD.distill_ledger(**kw)
    assert again["status"] == "LEARN_DEGRADED"
    assert again["reason"].startswith("no new graded rows")


def test_an_empty_ledger_is_degraded_not_silent(tmp_path):
    rec = RD.distill_ledger(as_of=AS_OF, rows=[], reputation={}, reputation_path=None,
                            autopsy={}, autopsy_path=None, local_fn=_refuse_local,
                            remote_fn=lambda p: pytest.fail("no facts, no call"),
                            spend_fn=_spend_zero, **_paths(tmp_path))
    assert rec["status"] == "LEARN_DEGRADED"
    assert rec["reason"].startswith("no new graded rows")


def test_a_rule_quoting_a_number_the_fact_lacks_is_refused():
    fact = {"fact_key": "k", "skill": 0.0556, "skill_all": 0.109, "base_rate": 0.147,
            "disc": 0.178, "mean_gap_per_day": None}
    assert RD.verify_rule_numbers("magnitude skill +5.56% at h=1", fact) is None
    assert RD.verify_rule_numbers("skill +5.6%", fact) is None
    assert RD.verify_rule_numbers("skill +12.40%", fact) is not None
    assert RD.verify_rule_numbers("skill -5.56%", fact) is not None   # sign flipped
    ok, bad = RD.parse_rules(json.dumps({"rules": [
        {"fact": "F1", "rule": "skill +12.40%"}, {"fact": "F9", "rule": "x"}]}), [fact])
    assert ok == [] and len(bad) == 2


def test_a_rule_whose_stance_contradicts_the_computed_verdict_is_refused():
    fact = {"fact_key": "k", "source": "graded_ledger", "skill": -0.7408,
            "skill_all": None, "base_rate": 0.267, "disc": 0.012, "n_date_blocks": 2,
            "mean_gap_per_day": None}
    assert RD.fact_verdict(fact) == "NO_DISCRIMINATION"
    ok, bad = RD.parse_rules(json.dumps({"rules": [
        {"fact": "F1", "rule": "Trust the forecast; skill -74.08%"}]}), [fact])
    assert ok == [] and "use/trust" in bad[0]
    ok, _ = RD.parse_rules(json.dumps({"rules": [
        {"fact": "F1", "rule": "Personas h=20: weight 0, skill -74.08%"}]}), [fact])
    assert len(ok) == 1
    ok, bad = RD.parse_rules(json.dumps({"rules": [
        {"fact": "F1", "rule": "Personas: weight 0."}]}), [fact])
    assert ok == [] and "no number" in bad[0]
    for text in ("SKILL: may be used at -74.08%",
                 "NO_DISCRIMINATION: weight 0; A_snapshot, skill -74.08%"):
        ok, bad = RD.parse_rules(json.dumps({"rules": [{"fact": "F1", "rule": text}]}),
                                 [fact])
        assert ok == [], text
    assert RD.fact_verdict({**fact, "skill": 0.05, "n_date_blocks": 8}) == "SKILL"
    assert RD.fact_verdict({**fact, "skill": 0.05, "n_date_blocks": 1}) == "UNPROVEN"


def test_the_decision_autopsy_becomes_a_fact_only_if_written_before_the_date():
    aut = {"written_utc": "2026-09-25T10:00:00+00:00", "headline": {"1": {
        "pair": "PROBE-REFUSED", "pooled_vs_universe_median": -0.0068,
        "n_rows_PROBE": 114, "n_rows_REFUSED": 41, "n_date_blocks": 3,
        "day_matched_t": -0.83,
        "day_matched_by_day": {"2026-09-21": -0.02, "2026-09-22": 0.0}}}}
    f = RD.autopsy_facts(aut, as_of=AS_OF)
    assert len(f) == 1 and f[0]["n"] == 155 and f[0]["brier"] is None
    assert RD.verify_rule_numbers("PROBE-REFUSED -0.68%/day: not a result", f[0]) is None
    assert RD.autopsy_facts(aut, as_of="2026-09-25") == []


def test_the_M2_month_writer_no_longer_erases_the_ledger_rules(tmp_path):
    RD.distill_ledger(as_of=AS_OF, rows=_ledger(), reputation={}, reputation_path=None,
                      autopsy={}, autopsy_path=None, local_fn=_refuse_local,
                      remote_fn=lambda p: (_reply_for(p), {"model": "deepseek/x"}),
                      spend_fn=_spend_zero, **_paths(tmp_path))
    RD.write_month("2026-09", [], {"model": "local_gguf (NOT ANSWERING)",
                                   "pending_model": "down"}, dir_=tmp_path)
    md = (tmp_path / "LEARNED_2026-09.md").read_text(encoding="utf-8")
    assert "skill" in md and "MEASURED" in md and "PENDING_MODEL" in md


# ─────────────────────────── retrieval sees MEASURED rules ──────────────────

def test_a_measured_rule_is_retrievable_after_its_date_and_not_on_it():
    fact = RD.ledger_facts(_ledger(), as_of=AS_OF, min_n=30)[0]
    row = RD.ledger_rule_row(fact, "text", as_of=AS_OF, answered_by="x",
                             local_status="ok", receipts={})
    assert LR.visible_at(row, date(2026, 9, 27)) == (True, None)
    assert LR.visible_at(row, date(2026, 9, 25))[0] is False
    forged = {**row, "hindsight_safe": None}
    assert LR.visible_at(forged, date(2026, 9, 27)) == (False, "rule_not_scored_yet")


# ─────────────────────────── policy_state moves only from grades ────────────

def _receipt(w_inv: float = 0.42, w_persona: float = 0.0) -> dict:
    return {"status": "OK", "date": "2026-09-25", "arms": [
        {"arm": "investigator:D_all", "weight": w_inv, "skill": 0.06, "n": 468},
        {"arm": "macro_rates", "weight": w_persona, "skill": -0.2, "n": 561}],
        "arms_by_observable": [
            {"arm": "investigator:D_all", "observable": "abs_move_exceeds",
             "horizon_days": 1.0, "n": 78, "skill": 0.055, "kind": "magnitude"},
            {"arm": "investigator:D_all", "observable": "return_sign",
             "horizon_days": 5.0, "n": 78, "skill": -0.087, "kind": "other"}]}


@pytest.fixture()
def ps_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "LEARNED_RULES", tmp_path / "no_rules.jsonl")
    monkeypatch.setattr(PS, "STATE_PATH", tmp_path / "policy_state.json")
    monkeypatch.setattr(PS, "JOURNAL_PATH", tmp_path / "policy_journal.jsonl")
    return tmp_path


GATE = {"verdict": "UNMEASURED_TRADE_SMALL", "sessions_graded": 0, "sessions_needed": 21}


def test_a_new_weight_writes_a_journal_line_with_its_receipt(ps_paths):
    s = PS.refresh(_receipt(), receipt_path="rep_25.json", persona_receipt="sb.json",
                   probe_gate=GATE)
    assert s["changed_since_last"] == ["reputation_weights", "persona_weights"]
    s2 = PS.refresh(_receipt(w_inv=0.40), receipt_path="rep_26.json",
                    persona_receipt="sb.json", probe_gate=GATE)
    assert s2["changed_since_last"] == ["reputation_weights"]
    lines = [json.loads(x) for x in PS.JOURNAL_PATH.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert lines[-1]["evidence"] == "rep_26.json"
    assert lines[-1]["old"] == {"investigator:D_all": 0.42}
    assert lines[-1]["new"] == {"investigator:D_all": 0.40}
    st = json.loads(PS.STATE_PATH.read_text(encoding="utf-8"))
    assert st["values"]["persona_weights"] == {"macro_rates": 0.0}
    assert st["observed"]["probe_gate"]["verdict"] == "UNMEASURED_TRADE_SMALL"
    dvm = st["observed"]["direction_vs_magnitude"]["by_family"]["investigator"]
    assert dvm["magnitude_skill_heldout"] == 0.055
    assert dvm["direction_skill_heldout"] == -0.087


def test_an_identical_receipt_journals_nothing_and_still_writes_the_file(ps_paths):
    PS.refresh(_receipt(), receipt_path="r.json", persona_receipt="s", probe_gate=GATE)
    n = len(PS.JOURNAL_PATH.read_text(encoding="utf-8").splitlines())
    before = PS.STATE_PATH.stat().st_mtime_ns
    s = PS.refresh(_receipt(), receipt_path="r.json", persona_receipt="s",
                   probe_gate=GATE, now="2026-09-27T00:00:00+00:00")
    assert s["changed_since_last"] == []
    assert len(PS.JOURNAL_PATH.read_text(encoding="utf-8").splitlines()) == n
    st = json.loads(PS.STATE_PATH.read_text(encoding="utf-8"))
    assert st["refreshed_utc"] == "2026-09-27T00:00:00+00:00"   # rewritten
    assert st["changed_since_last"] == [] and before is not None


def test_no_graded_rows_still_writes_the_file(ps_paths):
    s = PS.refresh({"status": "REFUSED", "reason": "no graded forecasts"},
                   receipt_path="r.json", persona_receipt=None, probe_gate=GATE)
    assert PS.STATE_PATH.is_file()
    assert s["changed_since_last"] == []
    assert s["observed"]["status"].startswith("RECEIPT_REFUSED")
    assert not PS.JOURNAL_PATH.exists()
    s = PS.refresh(None, probe_gate=GATE)
    assert s["observed"]["status"] == "NO_RECEIPT" and PS.STATE_PATH.is_file()


def test_refresh_never_moves_a_risk_limit_or_an_undeclared_key(ps_paths):
    s = PS.refresh(_receipt(), receipt_path="r", persona_receipt="s", probe_gate=GATE)
    assert set(s["values"]) == set(PS.SCHEMA)
    for k in ("MAX_INVESTED_FRAC", "MAX_NAME_FRAC", "MAX_ADV_PARTICIPATION"):
        assert k not in s["values"]
    with pytest.raises(PS.PolicyRefused):
        PS._check("reputation_weights", {"investigator:D_all": 1.5})


def test_facts_the_local_reader_skipped_go_to_deepseek(tmp_path):
    def half(prompt):
        obj = json.loads(_reply_for(prompt))
        return json.dumps({"rules": obj["rules"][:1]}), {"model": "local_gguf/local"}

    seen = []

    def remote(prompt):
        seen.append(prompt)
        return _reply_for(prompt), {"model": "deepseek/deepseek-chat"}

    rec = RD.distill_ledger(as_of=AS_OF, rows=_ledger(), reputation={},
                            reputation_path=None, autopsy={}, autopsy_path=None,
                            local_fn=half, remote_fn=remote, spend_fn=_spend_zero,
                            **_paths(tmp_path))
    assert rec["status"] == "LEARNED" and seen
    assert rec["n_rules_written"] == rec["n_facts"]
    assert rec["answered_by"] == "deepseek/deepseek-chat, local_gguf/local"


def test_direction_vs_magnitude_falls_back_to_the_rule_store(ps_paths, tmp_path):
    rules = tmp_path / "rules.jsonl"
    rules.write_text(chr(10).join(json.dumps(r) for r in [
        {"state": "MEASURED", "fact_key": "class:investigator|abs_move_exceeds|h1",
         "group": "investigator", "observable": "abs_move_exceeds", "horizon_days": 1,
         "n_heldout": 780, "skill": 0.0556, "kind": "magnitude"},
        {"state": "MEASURED", "fact_key": "class:investigator|return_sign|h5",
         "group": "investigator", "observable": "return_sign", "horizon_days": 5,
         "n_heldout": 780, "skill": -0.0872, "kind": "direction"}]), encoding="utf-8")
    rec = {k: v for k, v in _receipt().items() if k != "arms_by_observable"}
    s = PS.refresh(rec, receipt_path="r", persona_receipt="s", probe_gate=GATE,
                   rules_path=rules)
    dvm = s["observed"]["direction_vs_magnitude"]
    assert dvm["source"].startswith("learned_rules")
    assert dvm["by_family"]["investigator"]["magnitude_skill_heldout"] == 0.0556
    assert dvm["by_family"]["investigator"]["direction_skill_heldout"] == -0.0872
