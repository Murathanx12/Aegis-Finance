"""REVISED — a decision superseded by a re-run of the same ranking (spec §D).

`docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md` §D.
Two things are being pinned here and they are different in kind:

* the STATE MACHINE — `REVISED` at rank 3.5, monotone-in-rank still enforced,
  sibling exclusivity of `REFUSED`/`ORDER_SUBMITTED` untouched;
* the FIREWALL — `decision_contract.revise` takes candidate FIELDS (numbers the
  signal scorer already reads) and never text. An LLM string cannot revise a
  decision, and that is enforced by a refusal with a sentence, not by a
  convention nobody can test.

Everything is offline: a hand-built funnel state, the real registry YAML, the
real scorer, `tmp_path` for both the contract file and the ledger.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.services import decision_contract as DC
from backend.services import decision_ledger as DL

ASOF = date(2026, 9, 20)


# ── the state machine ───────────────────────────────────────────────────────

def test_revised_is_declared_and_ranked_between_seen_and_filled():
    assert "REVISED" in DC.DECISION_STATES
    assert DL.STATES == DC.DECISION_STATES
    assert set(DL.RANK) == set(DL.STATES), "every declared state needs a rank"
    assert DL.RANK["SEEN_BY_EXECUTOR"] < DL.RANK["REVISED"] < DL.RANK["FILLED"]
    assert DL.RANK["REFUSED"] < DL.RANK["REVISED"]
    # and inserting it moved nobody: the pre-existing ranks are unchanged
    assert [DL.RANK[s] for s in ("DECIDED", "DELIVERED", "SEEN_BY_EXECUTOR",
                                 "REFUSED", "ORDER_SUBMITTED", "FILLED",
                                 "SCORED")] == [0, 1, 2, 3, 3, 4, 5]


def test_rank_stays_monotone_with_revised_in_it(tmp_path):
    p = tmp_path / "ledger.jsonl"
    DL.record("d1", "DECIDED", by="t", path=p)
    DL.record("d1", "SEEN_BY_EXECUTOR", by="t", path=p)
    DL.record("d1", "REVISED", by="t", path=p)
    with pytest.raises(DL.DecisionLedgerError):
        DL.record("d1", "DELIVERED", by="t", path=p)      # backwards
    DL.record("d1", "SCORED", by="t", path=p)             # forwards is fine


def test_revised_before_decided_is_refused(tmp_path):
    p = tmp_path / "ledger.jsonl"
    with pytest.raises(DL.DecisionLedgerError) as exc:
        DL.record("never-heard-of-it", "REVISED", by="t", path=p)
    assert "before DECIDED" in str(exc.value)


def test_sibling_exclusivity_is_unchanged(tmp_path):
    p = tmp_path / "ledger.jsonl"
    DL.record("d2", "DECIDED", by="t", path=p)
    DL.record("d2", "REFUSED", by="t", path=p)
    with pytest.raises(DL.DecisionLedgerError):
        DL.record("d2", "ORDER_SUBMITTED", by="t", path=p,
                  allow_execution_states=True)
    # REVISED is nobody's sibling: a declined decision can still be superseded
    DL.record("d2", "REVISED", by="t", path=p)
    assert "REVISED" in DL.states_of("d2", path=p)


def test_revised_is_not_an_execution_artery_state():
    assert "REVISED" not in DL.EXECUTION_ARTERY_STATES


# ── a revision is a NEW id, never a rewritten one ───────────────────────────

def test_a_revision_id_differs_from_its_parent():
    kw = dict(policy_id="P", policy_version="v1", ticker="AAA",
              asof="2026-09-20")
    parent = DC.decision_id(**kw)
    child = DC.decision_id(**kw, revision_of=parent)
    assert parent != child
    assert DC.decision_id(**kw) == parent, "the old id must not move"


# ── the engine end: a real re-run over real scoring ─────────────────────────

def _candidates(quality_aaa: float = 0.90):
    return [
        {"ticker": "AAA", "price": 20.0, "quality": quality_aaa,
         "vol_annual": 0.40, "median_dollar_vol": 5e7, "market_cap": 9e8,
         "sector": "Industrials"},
        {"ticker": "BBB", "price": 30.0, "quality": 0.50,
         "vol_annual": 0.45, "median_dollar_vol": 6e7, "market_cap": 8e8,
         "sector": "Industrials"},
        {"ticker": "CCC", "price": 40.0, "quality": 0.20,
         "vol_annual": 0.50, "median_dollar_vol": 7e7, "market_cap": 7e8,
         "sector": "Industrials"},
    ]


def _state(cands):
    from backend.services import recommendation as REC
    from backend.services import signal_registry as SR

    return {"available": True,
            "recs": REC.score_candidates(cands, registry=SR.load()),
            "candidates": {c["ticker"]: c for c in cands},
            "books": {"built": {}, "refused": {}},
            "funnel_generated_at": "2026-09-20T00:00:00+00:00",
            "degradation_reasons": []}


@pytest.fixture()
def staged(tmp_path, monkeypatch):
    """Today's contract on disk, built from a hand-made funnel state."""
    monkeypatch.setattr(DC, "funnel_state",
                        lambda *a, **k: _state(_candidates()))
    monkeypatch.setattr(DC, "agency_options", lambda asof: ([], ""))
    rows = DC.build_daily_contracts(asof=ASOF, capital=1_000_000.0,
                                    out_dir=tmp_path)
    return {"dir": tmp_path, "rows": rows,
            "ledger": tmp_path / "ledger.jsonl"}


def _row_for(rows, ticker):
    return next(r for r in rows if r["ticker"] == ticker)


def test_an_llm_string_cannot_revise(staged):
    parent = _row_for(staged["rows"], "AAA")
    out = DC.revise(parent["decision_id"], asof=ASOF,
                    reason="the model says this looks very bullish",
                    candidate_updates={"AAA": {"quality": "very bullish"}},
                    out_dir=staged["dir"], ledger_path=staged["ledger"])
    assert out["status"] == "refused"
    assert "never text" in out["reason"]
    assert not staged["ledger"].exists(), "a refused revision writes nothing"


def test_a_structured_but_untyped_update_is_refused(staged):
    parent = _row_for(staged["rows"], "AAA")
    for bad in ({"AAA": {"quality": True}}, {"AAA": {"quality": [0.1]}},
                {"AAA": "quality=0.1"}):
        out = DC.revise(parent["decision_id"], asof=ASOF,
                        candidate_updates=bad, out_dir=staged["dir"],
                        ledger_path=staged["ledger"])
        assert out["status"] == "refused"


def test_a_rerun_that_changes_nothing_writes_nothing(staged):
    parent = _row_for(staged["rows"], "AAA")
    before = (staged["dir"] / f"{ASOF}.json").read_text(encoding="utf-8")
    out = DC.revise(parent["decision_id"], asof=ASOF, reason="no new event",
                    out_dir=staged["dir"], ledger_path=staged["ledger"])
    assert out["status"] == "unchanged"
    assert not staged["ledger"].exists()
    assert (staged["dir"] / f"{ASOF}.json").read_text(encoding="utf-8") == before


def test_a_direction_change_writes_a_child_and_revises_the_parent(staged):
    parent = _row_for(staged["rows"], "AAA")
    assert parent["direction"] in ("BUY", "WATCH")
    out = DC.revise(parent["decision_id"], asof=ASOF,
                    reason="typed event: gross profitability collapsed",
                    candidate_updates={"AAA": {"quality": 0.001}},
                    out_dir=staged["dir"], ledger_path=staged["ledger"])
    assert out["status"] == "revised"
    child = out["child"]
    assert child["decision_id"] != parent["decision_id"]
    assert child["parent_decision_id"] == parent["decision_id"]
    assert child["direction"] == "REFUSED"
    assert child["artifact_sha256"] == DC.seal(child)

    states = DL.states_of(parent["decision_id"], path=staged["ledger"])
    assert "REVISED" in states
    assert "DECIDED" in DL.states_of(child["decision_id"],
                                     path=staged["ledger"])

    # the parent row on disk is UNTOUCHED — it must stay gradeable exactly as
    # it was decided.
    blob = json.loads((staged["dir"] / f"{ASOF}.json").read_text(encoding="utf-8"))
    on_file = {r["decision_id"]: r for r in blob["rows"]}
    assert on_file[parent["decision_id"]] == parent
    assert child["decision_id"] in on_file


def test_the_reason_string_cannot_change_the_outcome(staged, tmp_path):
    parent = _row_for(staged["rows"], "AAA")
    update = {"AAA": {"quality": 0.001}}
    a = DC.revise(parent["decision_id"], asof=ASOF, reason="one story",
                  candidate_updates=update, out_dir=staged["dir"],
                  ledger_path=tmp_path / "a.jsonl")
    b = DC.revise(parent["decision_id"], asof=ASOF,
                  reason="a COMPLETELY different and much more exciting story",
                  candidate_updates=update, out_dir=staged["dir"],
                  ledger_path=tmp_path / "b.jsonl")
    skip = {"revision_reason", "built_utc", "artifact_sha256"}
    assert {k: v for k, v in a["child"].items() if k not in skip} == \
           {k: v for k, v in b["child"].items() if k not in skip}


def test_an_unknown_parent_is_refused_by_name(staged):
    out = DC.revise("0" * 16, asof=ASOF, out_dir=staged["dir"],
                    ledger_path=staged["ledger"])
    assert out["status"] == "refused"
    assert "CANNOT DETERMINE" in out["reason"]


def test_an_agency_book_row_is_not_name_revisable(tmp_path, monkeypatch):
    monkeypatch.setattr(DC, "funnel_state",
                        lambda *a, **k: _state(_candidates()))
    row = DC._base_row(policy_id="AGENCY_BALANCED", policy_version="h",
                       ticker="AGENCY_BOOK:balanced", asof=str(ASOF),
                       information_cutoff_utc=str(ASOF), uni_hash="h")
    row.update({"source": "agency", "direction": "BUY",
                "position_budget": {"capital_usd": 40_000.0}})
    DC.write_contracts([row], asof=ASOF, out_dir=tmp_path, capital=40_000.0)
    out = DC.revise(row["decision_id"], asof=ASOF, out_dir=tmp_path,
                    ledger_path=tmp_path / "ledger.jsonl")
    assert out["status"] == "refused"
    assert "book-level decision" in out["reason"]


def test_find_contract_row_reads_only_the_recent_window(staged):
    parent = _row_for(staged["rows"], "AAA")
    found, path = DC.find_contract_row(parent["decision_id"],
                                       out_dir=staged["dir"])
    assert found == parent and Path(path).name == f"{ASOF}.json"
    # a row older than the window is not found, and a revision of it is refused
    old = ASOF.replace(year=ASOF.year - 3)
    row = dict(parent, decision_id="a" * 16, asof=str(old))
    DC.write_contracts([row], asof=old, out_dir=staged["dir"],
                       capital=1_000_000.0)
    assert DC.find_contract_row("a" * 16, out_dir=staged["dir"]) == (None, None)
    assert DC.find_contract_row("a" * 16, out_dir=staged["dir"],
                                days=2000)[0] == row
