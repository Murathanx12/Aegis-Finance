"""N9 -- the precursor-library autopsy (re-test 3 of the failure thesis).

WHAT THESE TESTS PIN
====================
Everything runs against a STUBBED reader and a synthetic panel under
`tmp_path`. Nothing calls a provider, nothing opens `backend/data`, and no
dollar can be spent by this file -- which is the property the brief asks for
and the one an LLM job's tests most easily lose.

The four properties that make this job safe to run unattended:

1. **it files CANDIDATES, never library members** -- every row carries
   `status: "CANDIDATE"` and the admission path, because §37/§41's lesson is
   that a verdict which kills or admits is the hardest kind to notice being
   wrong;
2. **a reply that does not compile into the transferable vocabulary is
   REFUSED**, counted by class, and the refusal is written -- a refusal is a
   finding and belongs in the denominator;
3. **the cap is checked before every submission** and the spend printed is the
   CALL LEDGER's, never a constant (L2 reported a $2.38 run as free);
4. **it is resumable by cursor**, and a READER error does not pass the cursor
   (that row is retried) while every reply-level refusal does (it is never
   re-billed).
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd
import pytest

from backend.services.research_gym import autopsy as AU
from scripts import night_n9_library_autopsy as N


# --------------------------------------------------------------------------
# fixtures


GOOD_REPLY = json.dumps({
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

OFF_VOCABULARY_REPLY = json.dumps({
    "contemporaneous_evidence": ["a"], "post_outcome_evidence": ["b"],
    "proposed_mechanism": "m", "precursor_definition": "d",
    "affected_precursor": {"all": [{"feature": "put_call_ratio", "op": ">=",
                                    "value": 1.2}]},
    "unaffected_precursor": {"all": [{"feature": "vix", "op": "<", "value": 12}]},
    "falsifier": "f", "alternative_explanation": "r",
})


def _move(security="DIA", date="2018-02-01", tail="bottom"):
    return {"security": security, "date": date, "horizon_sessions": 20,
            "tail": tail, "forward_return_pct": -12.5,
            "state": {"vix": 31.0, "drawdown_pct": -8.2, "ret_1m_pct": -6.0,
                      "ret_3m_pct": -2.0, "ret_6m_pct": 3.0,
                      "realised_vol_20d": 28.0, "vol_ratio_20_60": 1.8,
                      "stress_pctile": 0.97, "security": security}}


class _Cap:
    """A cap that allows `n` submissions and then refuses, like the real one."""

    def __init__(self, n: int = 1000):
        self.n = n
        self.used = 0

    def may_submit(self) -> bool:
        return self.used < self.n

    def charge(self) -> None:
        self.used += 1

    def block(self) -> dict:
        return {"max_usd": 1.0, "rows_submitted": self.used}


def _frames(n_days: int = 400, seed: int = 11):
    """A two-security panel in `build_states`' own shape, no network."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2016-01-04", periods=n_days)
    out = {}
    for tkr in ("DIA", "XLV"):
        df = pd.DataFrame({
            "vix": rng.uniform(11, 40, n_days),
            "drawdown_pct": rng.uniform(-30, 0, n_days),
            "ret_1m_pct": rng.normal(0, 5, n_days),
            "ret_3m_pct": rng.normal(0, 8, n_days),
            "ret_6m_pct": rng.normal(0, 11, n_days),
            "realised_vol_20d": rng.uniform(8, 45, n_days),
            "vol_ratio_20_60": rng.uniform(0.6, 2.0, n_days),
            "stress_pctile": rng.uniform(0, 1, n_days),
            "security": tkr,
            "fwd_20": rng.normal(0, 6, n_days),
            "fwd_60": rng.normal(0, 10, n_days),
        }, index=idx)
        out[tkr] = df
    return out


# --------------------------------------------------------------------------
# 1. the declaration


def test_the_run_date_is_never_a_literal():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(N))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "RUN_DATE"
                for t in node.targets):
            assert not isinstance(node.value, ast.Constant)


def test_the_cap_comes_from_config_and_is_ten_dollars():
    from backend import config
    assert config.N9_LIBRARY_AUTOPSY_MAX_USD == 10.00
    assert N.max_usd_default() == 10.00


def test_the_held_panel_is_disjoint_from_n9s_selection_and_foreign_slices():
    """A precursor mined where it will later be scored is a memory."""
    from scripts.n9_mine_the_85 import (CONFIRM_SECURITIES,
                                        FOREIGN_SECURITIES, TRAIN_SECURITIES)
    assert set(N.HELD_SECURITIES) == set(CONFIRM_SECURITIES)
    assert not set(N.HELD_SECURITIES) & set(TRAIN_SECURITIES)
    assert not set(N.HELD_SECURITIES) & set(FOREIGN_SECURITIES)


def test_the_job_is_registered_resumable_and_staged():
    from scripts.night_factory_jobs import JOBS, JOB_STAGES, RESUMABLE
    assert "N9_library_autopsy" in JOBS
    assert JOB_STAGES["N9_library_autopsy"] == "signal"
    assert "N9_library_autopsy" in RESUMABLE


# --------------------------------------------------------------------------
# 2. the reply contract


def test_a_usable_reply_becomes_a_candidate():
    fields, refusal = N.parse_reply(GOOD_REPLY)
    assert refusal is None
    assert set(fields) == set(N._REQUIRED)


def test_a_reply_outside_the_transferable_vocabulary_is_refused_by_class():
    """N9's own finding: a rule the corpus cannot speak is untestable."""
    fields, refusal = N.parse_reply(OFF_VOCABULARY_REPLY)
    assert fields is None
    assert refusal["reason"] == "REFUSED_VOCABULARY"
    assert "put_call_ratio" in refusal["detail"]


def test_a_precursor_that_reads_the_outcome_is_refused():
    bad = json.loads(GOOD_REPLY)
    bad["affected_precursor"] = {"all": [{"feature": "fwd_20", "op": ">",
                                          "value": 0}]}
    fields, refusal = N.parse_reply(json.dumps(bad))
    assert fields is None
    assert refusal["reason"] in ("REFUSED_VOCABULARY", "REFUSED_SCHEMA")


def test_an_empty_falsifier_is_refused_as_not_falsifiable():
    bad = json.loads(GOOD_REPLY)
    bad["falsifier"] = "   "
    fields, refusal = N.parse_reply(json.dumps(bad))
    assert fields is None
    assert refusal["reason"] == "REFUSED_NOT_FALSIFIABLE"


def test_a_missing_field_is_a_schema_refusal_that_names_it():
    bad = json.loads(GOOD_REPLY)
    bad.pop("unaffected_precursor")
    fields, refusal = N.parse_reply(json.dumps(bad))
    assert refusal["reason"] == "REFUSED_SCHEMA"
    assert "unaffected_precursor" in refusal["detail"]


def test_prose_is_unparseable_not_repaired():
    fields, refusal = N.parse_reply("Here is my analysis: the market fell.")
    assert fields is None and refusal["reason"] == "REFUSED_UNPARSEABLE"


def test_a_fenced_reply_is_accepted_because_fences_are_the_only_repair():
    fields, refusal = N.parse_reply("```json\n" + GOOD_REPLY + "\n```")
    assert refusal is None and fields is not None


def test_every_refusal_class_is_declared():
    for cls in ("REFUSED_UNPARSEABLE", "REFUSED_SCHEMA", "REFUSED_VOCABULARY",
                "REFUSED_READER_ERROR", "REFUSED_NOT_FALSIFIABLE"):
        assert cls in N.REFUSAL_CLASSES


# --------------------------------------------------------------------------
# 3. the prompt


def test_the_prompt_carries_the_vocabulary_on_the_wire():
    """A prompt that refers to a schema it never sends is the 09-13 defect."""
    p = N.build_prompt(_move())
    for feat in AU.TRANSFERABLE_FEATURES:
        assert feat in p, feat
    assert "vol_ratio_20_60" in N.SCHEMA_HINT or "vol_ratio_20_60" in p


def test_the_prompt_tells_the_reader_what_the_library_already_says():
    p = N.build_prompt(_move())
    assert "vix" in p and "base rate" in p


def test_the_prompt_shows_the_move_and_its_horizon():
    p = N.build_prompt(_move())
    assert "-12.50%" in p and "20 sessions" in p and "bottom" in p


# --------------------------------------------------------------------------
# 4. candidates, never members


def test_every_filed_row_says_candidate_and_names_the_admission_path():
    row = N.candidate_row(_move(), json.loads(GOOD_REPLY),
                          backend="deepseek", incumbent_path="x.jsonl")
    assert row["status"] == "CANDIDATE"
    assert "library_measure" in row["admission_path"]
    assert "library_placebo_null" in row["admission_path"]
    assert row["candidate_id"] == N.move_key(_move())
    json.dumps(row)


def test_the_job_never_writes_into_the_library_itself():
    """The generator does not get to admit its own output (§37/§41)."""
    import inspect
    src = inspect.getsource(N)
    assert "library_candidates.jsonl" in src
    assert "measure_2006_2019.json" not in src
    assert N.CANDIDATE_STATUS == "CANDIDATE"


# --------------------------------------------------------------------------
# 5. the run loop: cursor, flush, cap


def test_candidates_are_filed_and_the_cursor_advances(tmp_path):
    moves = [_move(date=f"2018-02-0{i}") for i in range(1, 6)]
    out = N.autopsy_moves(moves, reader=lambda p: GOOD_REPLY,
                          backend="deepseek", cap=_Cap(), workers=1,
                          incumbent_path="x.jsonl",
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json")
    assert out["candidates_filed"] == 5 and out["n_refused"] == 0
    rows = [json.loads(x) for x in
            (tmp_path / "c.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5 and all(r["status"] == "CANDIDATE" for r in rows)
    cur = json.loads((tmp_path / "cur.json").read_text(encoding="utf-8"))
    assert len(cur["done"]) == 5


def test_a_second_run_re_bills_nothing(tmp_path):
    moves = [_move(date=f"2018-02-0{i}") for i in range(1, 4)]
    kw = dict(backend="deepseek", workers=1, incumbent_path="x.jsonl",
              candidates_file=tmp_path / "c.jsonl",
              cursor_file=tmp_path / "cur.json")
    N.autopsy_moves(moves, reader=lambda p: GOOD_REPLY, cap=_Cap(), **kw)
    calls = []

    def _never(prompt):
        calls.append(prompt)
        return GOOD_REPLY

    again = N.autopsy_moves(moves, reader=_never, cap=_Cap(), **kw)
    assert calls == [], "a resumed run re-asked for a move it had already paid for"
    assert again["moves_already_done"] == 3
    assert again["candidates_filed"] == 0


def test_a_reader_error_does_not_pass_the_cursor_and_is_retried(tmp_path):
    """A reader error is a property of the RUN; a schema refusal is a property
    of the reply to THAT move. The cursor rule differs and it is the whole
    reason `REFUSED_READER_ERROR` is its own class."""
    move = [_move()]
    kw = dict(backend="deepseek", workers=1, incumbent_path="x.jsonl",
              candidates_file=tmp_path / "c.jsonl",
              cursor_file=tmp_path / "cur.json")

    def _boom(prompt):
        raise RuntimeError("socket hung up")

    first = N.autopsy_moves(move, reader=_boom, cap=_Cap(), **kw)
    assert first["refusals"] == {"REFUSED_READER_ERROR": 1}
    assert json.loads((tmp_path / "cur.json").read_text(
        encoding="utf-8"))["done"] == []

    second = N.autopsy_moves(move, reader=lambda p: GOOD_REPLY, cap=_Cap(), **kw)
    assert second["candidates_filed"] == 1


def test_a_schema_refusal_is_never_re_billed(tmp_path):
    move = [_move()]
    kw = dict(backend="deepseek", workers=1, incumbent_path="x.jsonl",
              candidates_file=tmp_path / "c.jsonl",
              cursor_file=tmp_path / "cur.json")
    N.autopsy_moves(move, reader=lambda p: OFF_VOCABULARY_REPLY, cap=_Cap(),
                    **kw)
    calls = []
    N.autopsy_moves(move, reader=lambda p: calls.append(p) or GOOD_REPLY,
                    cap=_Cap(), **kw)
    assert calls == []


def test_the_cap_stops_the_run_before_the_submission_it_cannot_afford(tmp_path):
    moves = [_move(date=f"2018-02-0{i}") for i in range(1, 8)]
    calls = []
    out = N.autopsy_moves(moves,
                          reader=lambda p: calls.append(p) or GOOD_REPLY,
                          backend="deepseek", cap=_Cap(n=2), workers=1,
                          incumbent_path="x.jsonl",
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json")
    assert len(calls) == 2, "the cap did not bind before the third submission"
    assert out["stopped_on_cap"] is True
    assert out["candidates_filed"] == 2


def test_rows_are_flushed_before_the_run_ends(tmp_path):
    """A killed run keeps everything it has already paid for."""
    moves = [_move(date=f"2018-0{(i // 9) + 2}-0{(i % 9) + 1}")
             for i in range(12)]
    N.autopsy_moves(moves, reader=lambda p: GOOD_REPLY, backend="deepseek",
                    cap=_Cap(), workers=1, incumbent_path="x.jsonl",
                    flush_every=5, candidates_file=tmp_path / "c.jsonl",
                    cursor_file=tmp_path / "cur.json")
    rows = (tmp_path / "c.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == len({N.move_key(m) for m in moves})


def test_workers_above_one_still_files_every_row(tmp_path):
    moves = [_move(date=f"2018-02-{i:02d}") for i in range(1, 10)]
    out = N.autopsy_moves(moves, reader=lambda p: GOOD_REPLY,
                          backend="deepseek", cap=_Cap(), workers=4,
                          incumbent_path="x.jsonl",
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json")
    assert out["candidates_filed"] == 9


# --------------------------------------------------------------------------
# 6. the coverage read


def test_an_absent_incumbent_library_refuses_rather_than_reporting_zero(
        tmp_path):
    """An empty library makes every move 'unwarned' -- a number about the
    missing file, not about coverage."""
    got = N.load_incumbent(tmp_path / "nothing.jsonl")
    assert got["compiled"] == []
    assert "REFUSED" in got["refused"]


def test_the_incumbent_library_compiles_and_counts_what_it_could_not(tmp_path):
    p = tmp_path / "autopsies_2026-08-17.jsonl"
    p.write_text("\n".join([
        json.dumps({"autopsy": {"affected_precursor": {
            "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}),
        json.dumps({"autopsy": {"affected_precursor": {
            "all": [{"feature": "moon_phase", "op": ">=", "value": 1}]}}}),
        json.dumps({"autopsy": {}}),
    ]), encoding="utf-8")
    got = N.load_incumbent(p)
    assert got["n_rows"] == 3
    assert got["n_compiled"] == 1
    assert got["n_uncompilable"] == 2
    assert got["refused"] is None


def test_coverage_names_the_base_rate_beside_the_covered_share():
    """§51's point: 15% coverage against a 15% firing rate is lift 1.0."""
    frames = _frames()
    lib = [({"all": [{"feature": "vix", "op": ">=", "value": 35}]},
            AU.compile_precursor(
                {"all": [{"feature": "vix", "op": ">=", "value": 35}]},
                vocabulary=AU.TRANSFERABLE_FEATURES))]
    cov = N.unwarned_moves(frames, lib)
    assert cov["n_exceptional"] > 0
    assert cov["n_covered"] + cov["n_unwarned"] <= cov["n_exceptional"]
    assert cov["library_fires_on_share_of_all_days"] is not None
    assert cov["lift_vs_base_rate"] is not None
    assert cov["warning_window_sessions"] == N.WARNING_WINDOW_SESSIONS


def test_a_library_that_never_fires_leaves_every_move_unwarned():
    frames = _frames()
    never = [({"all": [{"feature": "vix", "op": ">=", "value": 9999}]},
              AU.compile_precursor(
                  {"all": [{"feature": "vix", "op": ">=", "value": 9999}]},
                  vocabulary=AU.TRANSFERABLE_FEATURES))]
    cov = N.unwarned_moves(frames, never)
    assert cov["n_covered"] == 0
    assert cov["n_unwarned"] == cov["n_exceptional"]


# --------------------------------------------------------------------------
# 7. the reader refusals


def test_reader_local_refuses_by_name_when_no_server_is_listening(monkeypatch):
    monkeypatch.setattr(N, "probe_local", lambda: "ProviderRefusal: no server")
    fn, backend, refusal = N.resolve_reader("local")
    assert fn is None and backend == "local_gguf"
    assert refusal.startswith("REFUSED_NO_LOCAL_SERVER")
    assert "never starts or stops a server" in refusal


def test_an_unknown_reader_is_refused_by_name():
    fn, _backend, refusal = N.resolve_reader("gpt")
    assert fn is None and refusal.startswith("REFUSED_UNKNOWN_READER")


def test_no_provider_is_refused_by_name(monkeypatch):
    import backend.services.llm_research as R
    monkeypatch.setattr(R, "available", lambda: (False, "no DEEPSEEK_API_KEY"))
    fn, _backend, refusal = N.resolve_reader("deepseek")
    assert fn is None and refusal.startswith("REFUSED_NO_PROVIDER")


# --------------------------------------------------------------------------
# 8. the receipt, end to end, with no money and no network


def test_the_receipt_refuses_by_name_with_no_reader(tmp_path, monkeypatch):
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "probe_local", lambda: "ProviderRefusal: down")
    out = N.N9_library_autopsy(smoke=True, reader="local", frames=_frames())
    assert out["reader"]["refused"].startswith("REFUSED_NO_LOCAL_SERVER")
    assert out["coverage"]["n_exceptional"] > 0
    assert out["autopsies"] is None
    assert out["output_is_candidates_only"]["status_on_every_row"] == "CANDIDATE"
    json.dumps(out, default=str)


def test_the_receipt_files_candidates_and_prints_the_ledgers_spend(
        tmp_path, monkeypatch):
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "resolve_reader",
                        lambda name: (lambda p: GOOD_REPLY, "local_gguf", None))
    out = N.N9_library_autopsy(smoke=True, reader="local", frames=_frames())
    assert out["autopsies"]["candidates_filed"] == 3
    assert out["spend"]["source"].endswith("read_calls()")
    assert "llm_spend_usd" in out
    assert out["cost_cap"]["max_usd"] == 10.0
    assert "CANDIDATE" in out["verdict"] or "SMOKE" in out["verdict"]
    rows = [json.loads(x) for x in
            (tmp_path / "library_candidates.jsonl").read_text(
                encoding="utf-8").splitlines()]
    assert rows and all(r["status"] == "CANDIDATE" for r in rows)
    json.dumps(out, default=str)


def test_the_spend_on_the_receipt_is_never_a_literal():
    """L2 carried a literal `llm_spend_usd` of 0.0 and reported a $2.384 run
    as free. A spend field that is a constant is not a measurement.

    Read as an AST, not as text: this file's own docstrings quote the banned
    pattern in order to explain it, and a grep-shaped guard that cannot tell an
    explanation from an instance forces the next reader to delete the
    explanation (CLAUDE.md, 2026-09-18).
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(N.__file__).read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, val in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant)
                    and key.value in ("llm_spend_usd", "cost_usd", "usd")
                    and isinstance(val, ast.Constant)):
                offenders.append(f"line {key.lineno}: {key.value} = "
                                 f"{val.value!r}")
    assert not offenders, offenders
    assert "spend_from_ledger" in ast.dump(tree)


# --------------------------------------------------------------------------
# 9. the cap must be able to BIND (2026-09-19, paid for by the first probe)
#
# The probe ran `--max-usd 1.0 --workers 2 --reader deepseek` for fifteen
# minutes. DeepSeek had renamed `deepseek-chat`'s served model to
# `deepseek-flash` on 2026-09-14, so every one of its 424 ledger rows came back
# with `cost_usd: null`, `spend_from_ledger` summed them as 0.0, and the $1.00
# cap read $0.00 the whole time while the balance moved $0.21.
#
# Two ways a cap stops being a cap, and both are now refusals by name.


_CALL_SEQ = itertools.count()


def _row(ts="2026-09-19T06:08:39+00:00", cost=None, model="deepseek-flash",
         purpose=N.PURPOSE):
    # A DISTINCT call_id per row: `read_calls` folds duplicates onto one base
    # row, so identical ids would make three calls read as one -- and the
    # de-duplication is right, the fixture was wrong.
    return {"call_id": f"c{next(_CALL_SEQ):06d}", "ts": ts,
            "purpose": purpose, "model": model, "cost_usd": cost,
            "tokens_in": 900, "tokens_out": 650, "cached_tokens": 0}


def _ledger(tmp_path, rows, name="llm_calls_2026-09.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                 encoding="utf-8")
    return tmp_path / "llm_calls.jsonl"          # the BASE; rotation is beside it


def test_an_unpriced_call_is_counted_and_names_the_model(tmp_path):
    base = _ledger(tmp_path, [_row(), _row(), _row(cost=0.001)])
    u = N.unpriced_calls("2026-09-19T06:00:00", path=base)
    assert u["n_unpriced"] == 2
    assert u["models"] == {"deepseek-flash": 2}
    assert "lower bound of zero" in u["why_it_is_a_breach"]


def test_a_priced_run_reports_no_unpriced_calls(tmp_path):
    base = _ledger(tmp_path, [_row(cost=0.001), _row(cost=0.002)])
    assert N.unpriced_calls("2026-09-19T06:00:00", path=base)["n_unpriced"] == 0


def test_rows_before_this_run_are_not_this_runs_breach(tmp_path):
    """The 424 rows the probe already wrote are unpriced for ever. A later run
    must be judged on ITS OWN calls or it could never start again."""
    base = _ledger(tmp_path, [_row(ts="2026-09-19T06:08:39+00:00"),
                              _row(ts="2026-09-20T10:00:00+00:00", cost=0.001)])
    u = N.unpriced_calls("2026-09-20T09:00:00", path=base)
    assert u["n_unpriced"] == 0


def test_another_jobs_unpriced_call_is_not_this_jobs_breach(tmp_path):
    base = _ledger(tmp_path, [_row(purpose="l2_event_extraction")])
    assert N.unpriced_calls("2026-09-19T06:00:00", path=base)["n_unpriced"] == 0


def test_the_run_stops_by_name_at_the_first_flush_that_sees_one(tmp_path):
    """Not at the end. The point of stopping is to stop SPENDING."""
    moves = [_move(date=f"2018-02-{i:02d}") for i in range(1, 12)]
    seen = {"n": 0}

    def check():
        seen["n"] += 1
        return ({"n_unpriced": 7, "models": {"deepseek-flash": 7}}
                if seen["n"] >= 2 else None)

    calls = []
    out = N.autopsy_moves(moves,
                          reader=lambda p: calls.append(p) or GOOD_REPLY,
                          backend="deepseek", cap=_Cap(), workers=1,
                          incumbent_path="x.jsonl", flush_every=3,
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json",
                          unpriced_check=check)
    assert out["stopped"] == N.REFUSED_UNPRICED_CALL
    assert "deepseek-flash" in out["stop_detail"]
    assert "lower bound of ZERO" in out["stop_detail"]
    assert len(calls) < len(moves), "the run did not stop; it finished"
    # everything already paid for is KEPT
    assert out["candidates_filed"] == 6
    assert len((tmp_path / "c.jsonl").read_text(
        encoding="utf-8").splitlines()) == 6


def test_a_run_that_finishes_inside_one_flush_window_is_still_checked(tmp_path):
    """Otherwise a short paid run could never trip the guard at all."""
    out = N.autopsy_moves([_move()], reader=lambda p: GOOD_REPLY,
                          backend="deepseek", cap=_Cap(), workers=1,
                          incumbent_path="x.jsonl", flush_every=50,
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json",
                          unpriced_check=lambda: {
                              "n_unpriced": 1,
                              "models": {"deepseek-flash": 1}})
    assert out["stopped"] == N.REFUSED_UNPRICED_CALL
    assert out["candidates_filed"] == 1


def test_a_priced_run_is_not_stopped(tmp_path):
    out = N.autopsy_moves([_move()], reader=lambda p: GOOD_REPLY,
                          backend="deepseek", cap=_Cap(), workers=1,
                          incumbent_path="x.jsonl",
                          candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json",
                          unpriced_check=lambda: None)
    assert out["stopped"] == "complete"


# ---- REFUSED_NO_LEDGER


def test_an_absent_ledger_directory_refuses_by_name(tmp_path):
    got = N.ledger_writable(tmp_path / "nope" / "llm_calls.jsonl")
    assert got["ok"] is False
    assert got["reason"] == N.REFUSED_NO_LEDGER
    assert "does not exist" in got["detail"]


def test_a_directory_with_no_ledger_stream_refuses_by_name(tmp_path):
    got = N.ledger_writable(tmp_path / "llm_calls.jsonl")
    assert got["ok"] is False and got["reason"] == N.REFUSED_NO_LEDGER
    assert "lower bound" in got["detail"]


def test_the_ROTATED_stream_satisfies_the_guard(tmp_path):
    """NOT `LLM_CALLS.exists()`. The ledger rotated to one file a month on
    2026-09-12 and the monolith is legitimately gone; a guard that demanded it
    could never go green, which is the `0/9 stamped [FAIL]` defect."""
    (tmp_path / "llm_calls_2026-09.jsonl").write_text(
        json.dumps(_row(cost=0.001)) + "\n", encoding="utf-8")
    got = N.ledger_writable(tmp_path / "llm_calls.jsonl")
    assert got["ok"] is True, got
    assert got["n_files"] == 1


def test_no_write_path_at_all_refuses(monkeypatch):
    """Telemetry resolving None means the calls are never ledgered, and a run
    whose calls are not ledgered cannot be capped."""
    from backend.services import llm_telemetry as tel
    monkeypatch.setattr(tel, "_resolve_path", lambda p: None)
    got = N.ledger_writable()
    assert got["ok"] is False and got["reason"] == N.REFUSED_NO_LEDGER


def test_a_paid_run_refuses_before_the_first_submission(tmp_path, monkeypatch):
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "ledger_writable", lambda *a, **k: {
        "ok": False, "reason": N.REFUSED_NO_LEDGER,
        "detail": "the ledger directory /nowhere does not exist."})

    def _never(name):
        return (lambda p: pytest.fail("a paid call was made with no ledger"),
                "deepseek", None)

    monkeypatch.setattr(N, "resolve_reader", _never)
    out = N.N9_library_autopsy(smoke=True, reader="deepseek", frames=_frames())
    assert out["verdict"].startswith(N.REFUSED_NO_LEDGER)
    assert out["autopsies"] is None
    assert out["ledger"]["ok"] is False
    json.dumps(out, default=str)


def test_an_unmetered_run_needs_no_ledger(tmp_path, monkeypatch):
    """A local reader costs compute, not dollars: no cap can bind, so a
    ledger guard there would be a gate that cannot go green."""
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "ledger_writable",
                        lambda *a, **k: pytest.fail("checked on a free run"))
    monkeypatch.setattr(N, "resolve_reader",
                        lambda name: (lambda p: GOOD_REPLY, "local_gguf", None))
    out = N.N9_library_autopsy(smoke=True, reader="local", frames=_frames())
    assert out["metered"] is False
    assert out["ledger"]["ok"] is True
    assert out["autopsies"]["candidates_filed"] == 3


# --------------------------------------------------------------------------
# 10. an interrupted run leaves a receipt
#
# The probe made 424 billed calls, filed 400 rows, and wrote NO receipt: the
# receipt is written by `night_factory_jobs.main()` only after the job function
# RETURNS, so a run that is killed leaves fifteen minutes of spend with nothing
# naming what it bought. That is the defect, and it is this job's to fix.


def test_an_interrupted_run_flushes_and_returns_rather_than_raising(tmp_path):
    moves = [_move(date=f"2018-02-{i:02d}") for i in range(1, 12)]
    calls = {"n": 0}

    def reader(prompt):
        calls["n"] += 1
        if calls["n"] > 6:
            raise KeyboardInterrupt("operator stopped the run")
        return GOOD_REPLY

    out = N.autopsy_moves(moves, reader=reader, backend="deepseek",
                          cap=_Cap(), workers=1, incumbent_path="x.jsonl",
                          flush_every=3, candidates_file=tmp_path / "c.jsonl",
                          cursor_file=tmp_path / "cur.json")
    assert out["stopped"] == "INTERRUPTED"
    assert "KeyboardInterrupt" in out["stop_detail"]
    assert out["candidates_filed"] == 6
    # AND THE ROWS ARE ON DISK, including the ones since the last flush
    assert len((tmp_path / "c.jsonl").read_text(
        encoding="utf-8").splitlines()) == 6
    cur = json.loads((tmp_path / "cur.json").read_text(encoding="utf-8"))
    assert len(cur["done"]) == 6, "a resumed run would re-bill these"


def test_an_interrupted_job_still_produces_a_receipt(tmp_path, monkeypatch):
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "ledger_writable", lambda *a, **k: {"ok": True,
                                                               "reason": None})
    calls = {"n": 0}

    def reader(prompt):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt("stopped")
        return GOOD_REPLY

    monkeypatch.setattr(N, "resolve_reader",
                        lambda name: (reader, "local_gguf", None))
    out = N.N9_library_autopsy(smoke=True, reader="local", frames=_frames())
    assert out["autopsies"]["stopped"] == "INTERRUPTED"
    assert out["verdict"].startswith("INTERRUPTED")
    assert "424 billed calls" in out["verdict"]
    assert out["autopsies"]["candidates_filed"] == 1
    json.dumps(out, default=str)


def test_the_receipt_says_when_its_spend_is_a_lower_bound(tmp_path,
                                                          monkeypatch):
    lib = tmp_path / "autopsies_2026-08-17.jsonl"
    lib.write_text(json.dumps({"autopsy": {"affected_precursor": {
        "all": [{"feature": "vix", "op": ">=", "value": 35}]}}}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(N, "ledger_writable", lambda *a, **k: {"ok": True,
                                                               "reason": None})
    monkeypatch.setattr(N, "resolve_reader",
                        lambda name: (lambda p: GOOD_REPLY, "deepseek", None))
    monkeypatch.setattr(N, "unpriced_calls", lambda *a, **k: {
        "n_unpriced": 3, "models": {"deepseek-flash": 3}})
    out = N.N9_library_autopsy(smoke=True, reader="deepseek", frames=_frames())
    assert out["spend_is_a_lower_bound"] is True
    assert "deepseek-flash" in out["spend_caveat"]
    assert "llm_cost_audit" in out["spend_caveat"]
    assert out["verdict"].startswith(N.REFUSED_UNPRICED_CALL)


def test_the_two_run_level_refusals_are_declared():
    assert N.REFUSED_UNPRICED_CALL == "REFUSED_UNPRICED_CALL"
    assert N.REFUSED_NO_LEDGER == "REFUSED_NO_LEDGER"
    # they are RUN-level, not document-level: a document cannot cause either,
    # so neither belongs in the per-reply refusal vocabulary.
    assert N.REFUSED_UNPRICED_CALL not in N.REFUSAL_CLASSES
    assert N.REFUSED_NO_LEDGER not in N.REFUSAL_CLASSES


def test_a_missing_incumbent_library_stops_the_job_before_any_call(
        tmp_path, monkeypatch):
    monkeypatch.setattr(N, "gym_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(N, "out_dir", lambda: tmp_path / "out")

    def _never(name):
        pytest.fail("a reader was resolved with no incumbent library")

    monkeypatch.setattr(N, "resolve_reader", _never)
    out = N.N9_library_autopsy(smoke=True, frames=_frames())
    assert "REFUSED" in out["verdict"]
