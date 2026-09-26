"""`llm_portfolio.void`: an APPEND-ONLY void row, never an edit.

Review 2026-09-26 (chunks D+E), adjudicated: `lib_mom_12_1_liqw_sealed_2026-09-26`
(97.5% in MU + SNDK, rho 0.90, MU printing in week one) is voided before
entry. A voided book is skipped by `grade` and the leaderboard and listed under
"voided before entry" with its reason; its twins stay.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from backend import config as C
from backend.services import llm_portfolio as LP


def _rec(name, book_id, *, kind="personal", parent=None, twin=None, asof="2026-09-26"):
    r = {"schema": LP.SCHEMA_VERSION, "name": name, "book_id": book_id, "kind": kind,
         "asof": asof, "objective": "x", "n_positions": 2, "horizon_days": [1],
         "benchmark": "SPY",
         "positions": [{"ticker": "AAA", "weight": 1.0}, {"ticker": "CASH", "weight": 0.0}]}
    if parent:
        r.update(parent_book_id=parent, twin=twin)
    return r


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    for r in (_rec("lib_x_sealed", "p1"), _rec("lib_x_sealed__ew", "t1", kind="twin",
                                                  parent="p1", twin="ew"),
              _rec("lib_y", "p2")):
        LP.append_book(r)
    return tmp_path


BEFORE = datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc)


def _bars():
    days = pd.bdate_range("2026-09-01", "2026-10-02")
    return pd.DataFrame([{"symbol": s, "date": d, "open": 10.0, "high": 10.0, "low": 10.0,
                          "close": 10.0, "volume": 1e6} for s in ("AAA", "SPY") for d in days])


def test_void_appends_one_row_and_edits_nothing(ledger):
    p = LP.books_path()
    before = p.read_text(encoding="utf-8")
    row = LP.void("p1", "VOID_BEFORE_ENTRY: concentration", who="tester", now=BEFORE)
    after = p.read_text(encoding="utf-8")
    assert after.startswith(before)                               # every old byte kept
    last = json.loads(after.splitlines()[-1])
    assert last == row and len(after.splitlines()) == len(before.splitlines()) + 1
    for k in ("schema", "book_id", "name", "reason", "voided_utc", "who"):
        assert k in row
    assert row["schema"] == "llm_portfolio/void" and row["name"] == "lib_x_sealed"


def test_a_voided_book_is_skipped_by_read_grade_and_leaderboard_and_listed(ledger):
    LP.void("p1", "VOID_BEFORE_ENTRY: concentration", who="tester", now=BEFORE)
    names = [b["name"] for b in LP.read_books()]
    assert "lib_x_sealed" not in names
    assert "lib_x_sealed__ew" in names and "lib_y" in names       # twins and others stay
    allb = LP.read_books(include_voided=True)
    v = next(b for b in allb if b["book_id"] == "p1")
    assert v["void"]["reason"].startswith("VOID_BEFORE_ENTRY")
    g = LP.grade(v, _bars(), today="2026-10-02")
    assert g["status"] == "VOIDED" and "concentration" in g["why"]
    lb = LP.leaderboard(allb, _bars(), today="2026-10-02")
    assert "p1" not in {r["book_id"] for r in lb["books"]}
    assert lb["voided_before_entry"][0]["book_id"] == "p1"
    assert lb["voided_before_entry"][0]["reason"].startswith("VOID_BEFORE_ENTRY")
    # a caller that read the books WITHOUT the voided one still gets the list
    lb2 = LP.leaderboard(LP.read_books(), _bars(), today="2026-10-02")
    assert [x["book_id"] for x in lb2["voided_before_entry"]] == ["p1"]
    # void rows are never books
    assert all(b.get("schema") != LP.VOID_SCHEMA for b in allb)


def test_void_refuses_twins_repeats_unknowns_blank_reasons_and_traded_books(ledger):
    with pytest.raises(LP.Refusal):
        LP.void("t1", "r", who="w", now=BEFORE)                   # a twin: void the parent
    with pytest.raises(LP.Refusal):
        LP.void("nope", "r", who="w", now=BEFORE)
    with pytest.raises(LP.Refusal):
        LP.void("p1", " ", who="w", now=BEFORE)
    with pytest.raises(LP.Refusal):                               # entry 09-28 has opened
        LP.void("p1", "r", who="w", now=datetime(2026, 9, 28, 14, tzinfo=timezone.utc))
    LP.void("p1", "r", who="w", now=BEFORE)
    with pytest.raises(LP.Refusal):
        LP.void("p1", "again", who="w", now=BEFORE)


def test_control_is_a_kind_a_book_may_declare():
    rec = LP.freeze({"name": "lib_z__control", "kind": "control", "objective": "o",
                     "model": "rule:strategy_library:z",
                     "freeze_gate": {"verdict": "CONTROL", "label": "CONTROL(EFFECTIVE_N)"},
                     "positions": [{"ticker": "AAA", "weight": 1.0, "thesis": "t",
                                    "falsifier": "f"},
                                   {"ticker": "CASH", "weight": 0.0, "thesis": "c",
                                    "falsifier": "n/a"}]})
    assert rec["kind"] == "control" and rec["freeze_gate"]["label"] == "CONTROL(EFFECTIVE_N)"
