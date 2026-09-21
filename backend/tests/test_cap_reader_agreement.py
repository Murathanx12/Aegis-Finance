"""Chunk 22c -- the cap reads the ledger the writer writes.

THE FAILURE THIS FILE EXISTS FOR
================================
2026-09-21, `night_factory_jobs N9_library_autopsy --max-usd 2 --workers 4
--reader deepseek`. The run stopped at "**$10.0479 of $2.00**" -- five times
its cap, $5.23 of real provider balance -- and its own receipt carried both
halves of the fault in adjacent keys:

    cap_block.estimated_spend_at_stop_usd   0.013238   (167 ledger reads)
    spend.usd                              10.047856   (8,342 calls)

Same file, same instant, two readers, a factor of 759. The cause was one
missing keyword: `_RunCap.refresh()` called `spend_from_ledger(since, path=...)`
and inherited that function's DEFAULT purpose, which is L2's
`l2_event_extraction`, while the receipt asked for `n9_library_autopsy`. The
cap was not loose and it was not unpriced -- it was watching a different meter,
and a cap that compares a number the writer never produced cannot bind at any
tolerance.

WHAT THESE TESTS PIN
====================
1. one reader for both -- `_RunCap.spend_now()` over N priced rows equals the
   receipt reader's usd, to the cent, for the job's OWN purpose;
2. another job's rows are not this run's spend, and the disagreement check is
   what SAYS SO rather than a comment;
3. a run whose two readers disagree ends `REFUSED_CAP_READER_DISAGREES`, at the
   FIRST flush, keeping every row already paid for;
4. the old wiring -- `purpose` left off -- is reproduced and shown to be the
   defect, so the regression has a corpse and not just a fix;
5. the tolerance mirrors one call's worst case and cannot drift from it.

Everything is under `tmp_path`. No network, no provider, no `backend/data`
read, and no LLM call: the readers are stubs and the ledgers are written here.
"""

from __future__ import annotations

import itertools
import json

import pytest

from backend import config
from backend.services import event_extraction as ex
from scripts import night_l2_typed_events as L2
from scripts import night_n9_library_autopsy as N


# --------------------------------------------------------------------------
# fixtures -- a ledger in tmp_path, never the real one


_SEQ = itertools.count()

SINCE = "2026-09-21T00:00:00+00:00"


def _row(*, purpose: str, cost: float | None = 0.001,
         ts: str = "2026-09-21T01:00:00+00:00") -> dict:
    # A DISTINCT call_id per row: `read_calls` folds duplicates onto one base
    # row, so identical ids would make N rows read as one.
    return {"call_id": f"cap{next(_SEQ):06d}", "ts": ts, "purpose": purpose,
            "model": "deepseek-chat", "cost_usd": cost,
            "tokens_in": 900, "tokens_out": 650, "cached_tokens": 0}


def _ledger(tmp_path, rows, name="llm_calls_2026-09.jsonl"):
    """Write the ROTATED file and hand back the BASE path, which is how the
    ledger has been shaped since 2026-09-12 (the monolith is legitimately
    gone; a reader that stats the base path alone sees nothing)."""
    (tmp_path / name).write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path / "llm_calls.jsonl"


def _cap(ledger, *, purpose: str | None = None, max_usd: float = 2.0):
    kw = {} if purpose is None else {"purpose": purpose}
    return L2._RunCap(max_usd, backend="deepseek", since_utc=SINCE,
                      ledger_path=ledger, **kw)


# --------------------------------------------------------------------------
# 1. one reader for both


def test_the_cap_and_the_receipt_read_the_same_number_for_n_priced_rows(
        tmp_path):
    """The property the $10.05 run did not have. Twelve priced rows written by
    the job, twelve counted by the cap, the same dollars either way."""
    rows = [_row(purpose=N.PURPOSE) for _ in range(12)]
    ledger = _ledger(tmp_path, rows)

    receipt = L2.spend_from_ledger(SINCE, purpose=N.PURPOSE, path=ledger)
    cap = _cap(ledger, purpose=N.PURPOSE)

    assert receipt["calls"] == 12
    assert receipt["usd"] > 0.0
    assert cap.ledger_calls == receipt["calls"]
    assert cap.spend_now() == pytest.approx(receipt["usd"], rel=1e-9)

    agree = cap.agreement(receipt)
    assert agree["agree"] is True
    assert agree["delta_usd"] == 0.0
    assert agree["delta_calls"] == 0
    assert agree["cap_purpose"] == agree["receipt_purpose"] == N.PURPOSE


def test_the_first_agreement_block_is_the_one_kept_on_the_receipt(tmp_path):
    """A disagreement is a property of the WIRING, so it is true at the first
    flush or never. A later read must not be able to absolve it."""
    ledger = _ledger(tmp_path, [_row(purpose=N.PURPOSE) for _ in range(3)])
    cap = _cap(ledger, purpose=N.PURPOSE)

    first = cap.agreement({"usd": 99.0, "calls": 9999, "purpose": "wrong"})
    assert first["agree"] is False
    cap.agreement(L2.spend_from_ledger(SINCE, purpose=N.PURPOSE, path=ledger))
    assert cap.first_flush_agreement is first
    assert cap.block()["first_flush_agreement"]["agree"] is False
    assert cap.block()["purpose"] == N.PURPOSE


# --------------------------------------------------------------------------
# 2. another job's rows are not this run's spend -- and the check says so


def test_another_jobs_rows_are_not_counted_and_the_check_is_what_says_so(
        tmp_path):
    """The 2026-09-21 shape, exactly: a handful of L2 rows in the window and
    thousands of N9 rows the cap never saw. Here the cap is wired to N9, so the
    L2 rows are invisible to it -- and the agreement block is the object that
    demonstrates it rather than a comment claiming it."""
    ledger = _ledger(tmp_path,
                     [_row(purpose=ex.PURPOSE) for _ in range(4)]
                     + [_row(purpose=N.PURPOSE) for _ in range(30)])

    cap = _cap(ledger, purpose=N.PURPOSE)
    assert cap.ledger_calls == 30, "the cap counted another job's rows"

    n9 = L2.spend_from_ledger(SINCE, purpose=N.PURPOSE, path=ledger)
    l2 = L2.spend_from_ledger(SINCE, purpose=ex.PURPOSE, path=ledger)
    assert l2["calls"] == 4 and n9["calls"] == 30

    assert cap.agreement(n9)["agree"] is True
    # ... and against the OTHER job's view the very same cap disagrees, which
    # is the whole point: the check has teeth, it is not vacuously true.
    wrong = cap.agreement(l2)
    assert wrong["agree"] is False
    assert wrong["delta_calls"] == 26
    assert wrong["cap_purpose"] == N.PURPOSE
    assert wrong["receipt_purpose"] == ex.PURPOSE


def test_the_old_wiring_is_the_defect_and_it_is_reproduced_here(tmp_path):
    """THE CORPSE. Build the cap the way run 3 built it -- `purpose` left to
    the default -- and the two readers separate by three orders of magnitude
    over the same file. Without this test the fix is a claim."""
    ledger = _ledger(tmp_path,
                     [_row(purpose=ex.PURPOSE, cost=0.0001) for _ in range(4)]
                     + [_row(purpose=N.PURPOSE, cost=0.01) for _ in range(300)])

    defective = _cap(ledger, purpose=None)        # the pre-22c call site
    receipt = L2.spend_from_ledger(SINCE, purpose=N.PURPOSE, path=ledger)

    assert defective.purpose == ex.PURPOSE, "the default is still L2's"
    assert defective.ledger_calls == 4
    assert receipt["calls"] == 300
    assert receipt["usd"] > 100 * defective.ledger_usd
    # the guard fires on exactly this
    assert defective.agreement(receipt)["agree"] is False


# --------------------------------------------------------------------------
# 3. a disagreement STOPS the run, at the first flush


class _StubCap:
    """Allows every submission; its agreement is whatever the test hands it."""

    def __init__(self, block: dict):
        self._block = block
        self.used = 0

    def may_submit(self) -> bool:
        return True

    def charge(self) -> None:
        self.used += 1

    def agreement(self, receipt_row):                            # pragma: no cover
        return self._block

    def block(self) -> dict:
        return {"max_usd": 2.0, "first_flush_agreement": self._block}


def _move(date="2018-02-05", security="DIA", tail="bottom"):
    """One exceptional move in `unwarned_moves`' own shape (see
    `test_n9_library_autopsy._move`)."""
    return {"security": security, "date": date, "horizon_sessions": 20,
            "tail": tail, "forward_return_pct": -12.5,
            "state": {"vix": 31.0, "drawdown_pct": -8.2, "ret_1m_pct": -6.0,
                      "ret_3m_pct": -2.0, "ret_6m_pct": 3.0,
                      "realised_vol_20d": 28.0, "vol_ratio_20_60": 1.8,
                      "stress_pctile": 0.97, "security": security}}


def _disagreement(cap_usd=0.013238, receipt_usd=10.047856,
                  cap_calls=167, receipt_calls=8342) -> dict:
    return {"cap_usd": cap_usd, "receipt_usd": receipt_usd,
            "cap_calls": cap_calls, "receipt_calls": receipt_calls,
            "agree": False,
            "delta_usd": abs(cap_usd - receipt_usd),
            "delta_calls": abs(cap_calls - receipt_calls),
            "tolerance_usd": config.CAP_READER_AGREEMENT_TOLERANCE_USD,
            "tolerance_calls": config.CAP_READER_AGREEMENT_TOLERANCE_CALLS,
            "cap_purpose": ex.PURPOSE, "receipt_purpose": N.PURPOSE,
            "cap_since_utc": SINCE, "receipt_since_utc": SINCE,
            "metered": True}


def test_a_run_whose_readers_disagree_stops_by_name_at_the_first_flush(
        tmp_path):
    """Run 3 would have stopped at row ~50 of 8,342 instead of at $10.05."""
    moves = [_move(date=f"2018-02-{i:02d}") for i in range(1, 16)]
    calls: list = []
    out = N.autopsy_moves(
        moves, reader=lambda p: calls.append(p) or _GOOD, backend="deepseek",
        cap=_StubCap(_disagreement()), workers=1, incumbent_path="x.jsonl",
        flush_every=3, candidates_file=tmp_path / "c.jsonl",
        cursor_file=tmp_path / "cur.json",
        agreement_check=lambda: _disagreement())

    assert out["stopped"] == N.REFUSED_CAP_READER_DISAGREES
    assert len(calls) < len(moves), "the run did not stop; it finished"
    assert out["candidates_filed"] == 3
    assert out["cap_reader_agreement"]["agree"] is False
    # the detail names BOTH reads, which is the thing nobody could see on the
    # night: the cap figure was printed with nothing beside it.
    for token in ("0.013238", "10.047856", "167", "8342",
                  N.PURPOSE, ex.PURPOSE):
        assert str(token) in out["stop_detail"]
    # everything already paid for is KEPT
    assert len((tmp_path / "c.jsonl").read_text(
        encoding="utf-8").splitlines()) == 3


def test_the_two_reads_are_printed_side_by_side_not_logged_into_a_void(
        tmp_path, capsys):
    """`night_factory_jobs` calls no `basicConfig`, so the root logger sits at
    WARNING: an INFO-only guard would report where nobody reads. The operator
    sees BOTH figures on one line or the guard has not done its job."""
    N.autopsy_moves(
        [_move()], reader=lambda p: _GOOD, backend="deepseek",
        cap=_StubCap({"agree": True}), workers=1, incumbent_path="x.jsonl",
        flush_every=50, candidates_file=tmp_path / "c.jsonl",
        cursor_file=tmp_path / "cur.json",
        agreement_check=lambda: {**_disagreement(), "agree": True})
    printed = capsys.readouterr().out
    assert "cap-reader agreement" in printed
    for token in ("0.013238", "10.047856", "167", "8342", "AGREE"):
        assert str(token) in printed


def test_agreeing_readers_do_not_stop_the_run_and_are_asked_once(tmp_path):
    """A guard that cannot go green is a broken guard -- and a ledger scan per
    flush would cost more than the rows it protects."""
    asked = {"n": 0}

    def check():
        asked["n"] += 1
        return {**_disagreement(), "agree": True}

    moves = [_move(date=f"2018-03-{i:02d}") for i in range(1, 13)]
    out = N.autopsy_moves(
        moves, reader=lambda p: _GOOD, backend="deepseek",
        cap=_StubCap({"agree": True}), workers=1, incumbent_path="x.jsonl",
        flush_every=3, candidates_file=tmp_path / "c.jsonl",
        cursor_file=tmp_path / "cur.json", agreement_check=check)

    assert out["stopped"] == "complete"
    assert out["candidates_filed"] == 12
    assert asked["n"] == 1, "the wiring is checked once, not per flush"
    assert out["cap_reader_agreement"]["agree"] is True


def test_a_run_that_finishes_inside_one_flush_window_is_still_checked(
        tmp_path):
    """Otherwise a short paid run could never trip the guard at all -- the same
    hole the unpriced check had to close."""
    out = N.autopsy_moves(
        [_move()], reader=lambda p: _GOOD, backend="deepseek",
        cap=_StubCap(_disagreement()), workers=1, incumbent_path="x.jsonl",
        flush_every=50, candidates_file=tmp_path / "c.jsonl",
        cursor_file=tmp_path / "cur.json",
        agreement_check=lambda: _disagreement())

    assert out["stopped"] == N.REFUSED_CAP_READER_DISAGREES
    assert out["candidates_filed"] == 1


def test_a_job_with_no_agreement_check_is_unchanged(tmp_path):
    """The local/unmetered path and every existing caller keep working."""
    out = N.autopsy_moves(
        [_move()], reader=lambda p: _GOOD, backend="local_gguf",
        cap=_StubCap({"agree": True}), workers=1, incumbent_path="x.jsonl",
        flush_every=50, candidates_file=tmp_path / "c.jsonl",
        cursor_file=tmp_path / "cur.json")
    assert out["stopped"] == "complete"
    assert out["cap_reader_agreement"] is None


# --------------------------------------------------------------------------
# 4. the declarations


def test_the_third_run_level_refusal_is_declared_and_enumerated():
    assert N.REFUSED_CAP_READER_DISAGREES == "REFUSED_CAP_READER_DISAGREES"
    # run-level, not document-level: no reply can cause it.
    assert N.REFUSED_CAP_READER_DISAGREES not in N.REFUSAL_CLASSES
    # and every site that enumerates the cap's refusals carries it.
    assert N.REFUSED_CAP_READER_DISAGREES in N.CAP_REFUSALS
    assert set(N.CAP_REFUSALS) == {N.REFUSED_UNPRICED_CALL,
                                   N.REFUSED_NO_LEDGER,
                                   N.REFUSED_CAP_READER_DISAGREES}
    assert N.REFUSED_CAP_READER_DISAGREES in N.__doc__


def test_the_tolerance_is_one_calls_worst_case_and_cannot_drift(tmp_path):
    """Mirrored, not guessed. If `investigator_night` re-prices a worst-case
    call, this constant moves with it or this test goes red."""
    from backend.services import investigator_night as IN
    assert (config.CAP_READER_AGREEMENT_TOLERANCE_USD
            == IN.WORST_CASE_CALL_USD)
    assert config.CAP_READER_AGREEMENT_TOLERANCE_CALLS == 1

    # one call of slack is tolerated; two are not
    ledger = _ledger(tmp_path, [_row(purpose=N.PURPOSE, cost=0.001)
                                for _ in range(10)])
    cap = _cap(ledger, purpose=N.PURPOSE)
    near = cap.agreement({"usd": cap.ledger_usd + 0.001, "calls": 11,
                          "purpose": N.PURPOSE})
    assert near["agree"] is True
    far = cap.agreement({"usd": cap.ledger_usd + 0.001, "calls": 12,
                         "purpose": N.PURPOSE})
    assert far["agree"] is False


def test_an_unmetered_run_has_no_bill_for_two_readers_to_disagree_about(
        tmp_path):
    """A local reader costs compute, not dollars. A refusal there would be a
    gate that fires on work which cannot produce a bill."""
    ledger = _ledger(tmp_path, [_row(purpose=N.PURPOSE) for _ in range(5)])
    cap = L2._RunCap(1.0, backend="local_gguf", since_utc=SINCE,
                     ledger_path=ledger, purpose=N.PURPOSE)
    block = cap.agreement({"usd": 99.0, "calls": 9999, "purpose": "anything"})
    assert block["agree"] is True
    assert block["metered"] is False


# --------------------------------------------------------------------------
# 5. L2, the job that lent N9 the class


def test_l2s_cap_and_l2s_receipt_read_the_same_purpose(tmp_path):
    """L2 never had N9's defect -- both of its readers fell back to the SAME
    default -- but the agreement was coincidental rather than stated, which is
    what let N9 inherit the wrong purpose in silence. Both call sites now name
    it, and this is the test that keeps them equal."""
    import ast
    from pathlib import Path

    src = Path(L2.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    cap_purposes, ledger_purposes = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in ("_RunCap", "spend_from_ledger"):
            continue
        for kw in node.keywords:
            if kw.arg == "purpose":
                (cap_purposes if name == "_RunCap"
                 else ledger_purposes).append(ast.unparse(kw.value))
    assert cap_purposes == ["ex.PURPOSE"], cap_purposes

    # and the numbers agree on a real ledger
    ledger = _ledger(tmp_path,
                     [_row(purpose=ex.PURPOSE) for _ in range(7)]
                     + [_row(purpose=N.PURPOSE) for _ in range(20)])
    cap = L2._RunCap(2.0, backend="deepseek", since_utc=SINCE,
                     ledger_path=ledger, purpose=ex.PURPOSE)
    receipt = L2.spend_from_ledger(SINCE, path=ledger)   # L2's own receipt call
    assert cap.agreement(receipt)["agree"] is True
    assert receipt["calls"] == 7


def test_every_production_cap_names_its_purpose(tmp_path):
    """The one keyword that cost $5.23 of billed provider balance.

    `_RunCap.purpose` KEEPS its `ex.PURPOSE` default -- removing it would
    break the class's own history and this file's corpse test above -- so the
    default is made safe HERE instead: every `_RunCap(...)` under `scripts/`
    names its purpose, and a third job that borrows the class the way N9 did
    goes red before it can spend rather than after."""
    import ast
    from pathlib import Path

    root = Path(N.__file__).resolve().parent
    sites: list[str] = []
    for src in sorted(root.glob("*.py")):
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (getattr(node.func, "id", None) or
                    getattr(node.func, "attr", None)) != "_RunCap":
                continue
            where = f"{src.name}:{node.lineno}"
            sites.append(where)
            assert "purpose" in [kw.arg for kw in node.keywords], (
                f"{where}: a _RunCap built without `purpose` inherits L2's, "
                f"which is the 2026-09-21 defect")
    assert len(sites) >= 2, (
        f"expected N9's and L2's cap call sites, found {sites}")


_GOOD = json.dumps({
    "contemporaneous_evidence": ["realised vol had doubled in three weeks"],
    "post_outcome_evidence": ["the index fell 14% over the next month"],
    "proposed_mechanism": "vol-of-vol expansion precedes gap risk",
    "precursor_definition": "short-window vol more than 1.4x long-window vol "
                            "while the security sits below its 252d high",
    "affected_precursor": {"all": [{"feature": "vol_ratio_20_60", "op": ">=",
                                    "value": 1.4},
                                   {"feature": "drawdown_pct", "op": "<=",
                                    "value": -5.0}]},
    "unaffected_precursor": {"all": [{"feature": "vol_ratio_20_60", "op": "<",
                                      "value": 0.9}]},
    "falsifier": "no excess of tail moves in the affected region out of sample",
    "alternative_explanation": "it is just the VIX in a different coordinate",
})
