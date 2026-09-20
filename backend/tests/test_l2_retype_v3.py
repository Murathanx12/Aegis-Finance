"""Vocabulary v3 and the `L2_retype_v3` idle job.

WHAT THESE TESTS PIN
====================
1. **both new ids are ON THE WIRE.** The 2026-09-13 defect was a prompt that
   referred to a schema it never sent and lost 54% of its first flush to
   invented ids. An id that exists in the table and not in the system prompt is
   an id the model cannot choose.
2. **the entity fields do not break v2 rows.** `entities` is optional by
   construction, so every v2 reply and every v2 row on disk still validates.
3. **the screen is DECLARED and printed**, and the receipt says it is a screen:
   no rate may be quoted from a screened denominator.
4. **the job refuses by name when no server is listening**, and never starts
   one.

Every test uses a fake reader and `tmp_path`. Nothing calls a model and nothing
under `backend/data` is written.
"""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from backend.services import event_extraction as ex
from backend.services import event_vocabulary as vocab
from scripts import night_l2_retype_v3 as R


# --------------------------------------------------------------------------
# fixtures


class _Reply:
    def __init__(self, text: str, model: str = "qwen2.5-7b"):
        self.text = text
        self.tokens_in = 100
        self.tokens_out = 40
        self.cost_usd = 0.0
        self.latency_s = 0.4
        self.model = model


def _reply(event_type: str = "foreign_entrant_capacity", **extra) -> str:
    row = {"event_type": event_type, "direction": -1,
           "magnitude_bucket": "MODERATE", "confidence": 0.7,
           "evidence_span": "qualification"}
    row.update(extra)
    return json.dumps(row)


def _fake(text: str):
    def complete(backend, prompt, **kw):
        return _Reply(text)
    return complete


def _corpus_row(raw_id: str, title: str, body: str = "") -> dict:
    return {"source": "alpaca", "raw_id": raw_id,
            "first_seen_utc": "2026-09-18T12:00:00+00:00",
            "published_utc": "2026-09-18T11:59:00+00:00",
            "pit_grade": "native_stamp", "tickers": ["MU"],
            "url": "https://example.invalid/x",
            "title": title, "body": body}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """No corpus, no panel, no write outside tmp_path."""
    monkeypatch.setattr(R, "typed_dir", lambda: tmp_path / "typed")
    monkeypatch.setattr(R, "out_dir", lambda: tmp_path / "out")
    monkeypatch.setattr(R, "corpus_files", lambda *a, **k: [])
    monkeypatch.setattr(R, "read_rows", lambda files: ([], []))
    monkeypatch.setattr(R, "panel_units", lambda *a, **k: [])
    return tmp_path


# --------------------------------------------------------------------------
# 1. the vocabulary is on the wire


def test_both_new_ids_are_in_the_current_table():
    assert "foreign_entrant_capacity" in vocab.EVENT_TYPES
    assert "growth_constraint_cited" in vocab.EVENT_TYPES
    assert vocab.VOCABULARY_VERSION == 3
    assert vocab.EVENT_TYPES[-1] == "no_event"


def test_both_new_ids_are_ON_THE_WIRE_in_the_system_prompt():
    """2026-09-13: a prompt referred to a schema it never sent and DeepSeek
    refused 54% of the first flush for ids it invented."""
    for variant in ("A", "B"):
        wire = ex.system_with_schema(variant)
        assert "foreign_entrant_capacity" in wire, variant
        assert "growth_constraint_cited" in wire, variant
        # not just in the enum list -- in the schema the prompt sends too
        assert wire.count("foreign_entrant_capacity") >= 2, variant


def test_the_schema_enum_is_generated_and_carries_45_ids():
    assert ex.SCHEMA["properties"]["event_type"]["enum"] == list(vocab.EVENT_TYPES)
    assert len(ex.SCHEMA["properties"]["event_type"]["enum"]) == 45


def test_both_prompts_explain_the_entity_fields():
    for prompt in (ex.SYSTEM_PROMPT, ex.SYSTEM_PROMPT_B):
        low = prompt.lower()
        assert "entities" in low
        assert "incumbent" in low and "entrant" in low
        assert "supplier" in low and "named_input" in low


# --------------------------------------------------------------------------
# 2. the entity fields, and v2 compatibility


def test_a_v2_shaped_reply_still_validates_and_carries_no_entities():
    """The compatibility property, stated as a test rather than as a hope."""
    row = ex.parse_reply(json.dumps({
        "event_type": "earnings_report", "direction": 1,
        "magnitude_bucket": "MODERATE", "confidence": 0.8,
        "evidence_span": "beat"}))
    assert isinstance(row, ex.TypedEventRow)
    assert row.entities == {}
    assert row.vocabulary_version == 3


def test_entities_is_not_required_by_the_schema():
    assert "entities" not in ex.SCHEMA["required"]
    assert "entities" in ex.SCHEMA["properties"]


def test_the_entity_block_is_read_onto_the_row():
    row = ex.parse_reply(_reply(entities={"incumbent": "Micron",
                                          "entrant": "CXMT"}))
    assert isinstance(row, ex.TypedEventRow)
    assert row.entities == {"incumbent": "Micron", "entrant": "CXMT"}
    assert row.as_dict()["entities"]["entrant"] == "CXMT"


def test_named_input_is_carried_for_the_constraint_id():
    row = ex.parse_reply(json.dumps({
        "event_type": "growth_constraint_cited", "direction": -1,
        "magnitude_bucket": "MODERATE", "confidence": 0.6,
        "evidence_span": "we could ship more if we could get HBM",
        "entities": {"supplier": "SK Hynix", "named_input": "HBM supply"}}))
    assert isinstance(row, ex.TypedEventRow)
    assert row.entities["named_input"] == "HBM supply"


def test_entities_on_an_id_that_declares_none_is_dropped_and_named():
    """A field that can appear anywhere is a field no reader can filter on --
    so the block never lands on such a row. 2026-09-20: it used to be a
    refusal of the whole row, and two nights of the 7B reader lost 30% of
    their rows to it; the type was valid every time. The block is dropped,
    the row is kept, and the drop is on the row."""
    out = ex.parse_reply(json.dumps({
        "event_type": "earnings_report", "direction": 1,
        "magnitude_bucket": "MODERATE", "confidence": 0.8,
        "evidence_span": "beat", "entities": {"incumbent": "Micron"}}))
    assert isinstance(out, ex.TypedEventRow)
    assert out.event_type == "earnings_report" and out.entities == {}
    assert out.entities_dropped == ("incumbent",)
    assert out.as_dict()["entities_dropped"] == ["incumbent"] or \
        out.as_dict()["entities_dropped"] == ("incumbent",)


def test_a_stray_unknown_key_on_a_roleless_id_is_dropped_too():
    out = ex.parse_reply(json.dumps({
        "event_type": "analyst_rating_change", "direction": 1,
        "magnitude_bucket": "MODERATE", "confidence": 0.7,
        "evidence_span": "upgrade", "entities": {"analyst": "Goldman"}}))
    assert isinstance(out, ex.TypedEventRow)
    assert out.entities_dropped == ("analyst",)


def test_a_stray_block_does_not_rescue_a_row_with_another_fault():
    out = ex.parse_reply(json.dumps({
        "event_type": "earnings_report", "direction": 7,
        "magnitude_bucket": "MODERATE", "confidence": 0.8,
        "evidence_span": "beat", "entities": {"incumbent": "Micron"}}))
    assert isinstance(out, ex.Refusal)
    assert out.reason == "REFUSED_SCHEMA"
    assert "direction" in out.detail


def test_an_unknown_entity_role_is_refused_and_names_what_is_allowed():
    out = ex.parse_reply(_reply(entities={"customer": "Dell"}))
    assert isinstance(out, ex.Refusal)
    assert "customer" in out.detail and "incumbent" in out.detail


def test_an_over_long_entity_value_is_refused():
    out = ex.parse_reply(_reply(entities={"incumbent": "x" * 500}))
    assert isinstance(out, ex.Refusal)
    assert str(ex.ENTITY_CHARS) in out.detail


def test_the_entity_priors_are_per_role_and_declared():
    assert vocab.ENTITY_DIRECTION_PRIORS["foreign_entrant_capacity"] == {
        "incumbent": -1, "entrant": +1}
    assert vocab.ENTITY_DIRECTION_PRIORS["growth_constraint_cited"] == {
        "issuer": -1, "supplier": +1}


# --------------------------------------------------------------------------
# 3. the screen


def test_the_prefilter_is_declared_per_target_id():
    assert set(R.PREFILTER) == set(R.TARGET_IDS)
    assert set(R.TARGET_IDS) == set(vocab.IDS_WITH_ENTITIES)
    for terms in R.PREFILTER.values():
        assert terms and all(isinstance(t, str) and t for t in terms)


def test_the_receipt_prints_the_terms_and_says_it_is_a_screen():
    d = R.prefilter_declaration()
    assert d["terms"] == {k: list(v) for k, v in R.PREFILTER.items()}
    assert len(d["prefilter_sha256"]) == 16
    assert "recall is UNKNOWN" in d["it_is_a_SCREEN"]
    assert "No RATE may be quoted" in d["it_is_a_SCREEN"]


def test_a_matching_text_is_screened_in_and_names_which_id():
    assert R.prefilter_hits("CXMT DDR5 passes AM5 qualification") == [
        "foreign_entrant_capacity"]
    assert R.prefilter_hits("HBM is the binding constraint this year") == [
        "growth_constraint_cited"]


def test_a_text_matching_neither_group_is_skipped():
    assert R.prefilter_hits("Acme declares a quarterly dividend of $0.10") == []


def test_the_match_is_case_insensitive():
    assert R.prefilter_hits("BOTTLENECK") == ["growth_constraint_cited"]


def test_a_text_may_match_both_groups():
    hits = R.prefilter_hits("qualification of a domestic rival is a bottleneck")
    assert set(hits) == set(R.TARGET_IDS)


# --------------------------------------------------------------------------
# 4. candidate selection and resume


def test_only_screened_in_rows_become_candidates(monkeypatch):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification"),
            _corpus_row("b", "Acme declares a dividend"),
            _corpus_row("c", "HBM is our binding constraint")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    plan = R.candidate_units()
    assert plan["stats"]["corpus_rows"] == 3
    assert plan["stats"]["screened_in"] == 2
    assert len(plan["units"]) == 2
    assert all(u["prefilter_hits"] for u in plan["units"])


def test_a_text_already_re_read_is_not_asked_again(monkeypatch, tmp_path):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    first = R.candidate_units()
    assert len(first["units"]) == 1
    h = first["units"][0]["text_sha256"]

    d = tmp_path / "typed"
    d.mkdir(parents=True, exist_ok=True)
    # A PAST run's file. The name is derived from a date that is not today's
    # on purpose: the resume reads the rows on disk, not a file whose name
    # happens to match the current run's.
    (d / "retype_v3_2020-01-02.jsonl").write_text(
        json.dumps({"text_sha256": h}) + "\n", encoding="utf-8")

    again = R.candidate_units()
    assert again["units"] == []
    assert again["stats"]["already_read"] == 1


def test_a_refusal_row_also_counts_as_asked(monkeypatch, tmp_path):
    """A text the reader refused was asked and read; re-asking it every night
    is the loop 2026-09-10's replay is the standing lesson about."""
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    h = R.candidate_units()["units"][0]["text_sha256"]
    d = tmp_path / "typed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "retype_v3_2020-01-03.jsonl").write_text(
        json.dumps({"text_sha256": h, "reason": "REFUSED_SCHEMA"}) + "\n",
        encoding="utf-8")
    assert R.candidate_units()["units"] == []


def test_the_candidate_list_is_ordered_and_hashed(monkeypatch):
    rows = [_corpus_row(str(i), f"qualification number {i}") for i in range(5)]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    a = R.candidate_units()["units"]
    b = R.candidate_units()["units"]
    assert [u["text_sha256"] for u in a] == [u["text_sha256"] for u in b]
    fa, fb = R.units_fingerprint(a), R.units_fingerprint(b)
    assert fa == fb and fa["n_units"] == 5


def test_max_rows_truncates_and_says_so(monkeypatch):
    rows = [_corpus_row(str(i), f"qualification {i}") for i in range(10)]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    plan = R.candidate_units(max_rows=3)
    assert len(plan["units"]) == 3
    assert plan["truncated_at"] == 3


# --------------------------------------------------------------------------
# 5. the job


def test_no_server_listening_is_PENDING_MODEL_with_the_list_frozen(
        monkeypatch):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    monkeypatch.setattr(R, "_probe", lambda backend: "ProviderRefusal: no server")
    out = R.L2_retype_v3(smoke=True)
    assert out["verdict"].startswith("PENDING_MODEL")
    assert "no server" in out["verdict"]
    assert out["candidate_fingerprint"]["n_units"] == 1
    assert out["typed"] == 0
    json.dumps(out, default=str)


def test_the_job_never_starts_or_stops_a_server():
    """AST, not grep: the docstring names the ban in order to state it, and a
    grep-shaped guard cannot tell an explanation from an instance."""
    src = Path(R.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = set()
    for c in calls:
        f = c.func
        if isinstance(f, ast.Attribute):
            names.add(f.attr)
        elif isinstance(f, ast.Name):
            names.add(f.id)
    assert "stop" not in names and "start" not in names
    assert "stop_if_owned" not in names
    assert "llama_server" not in ast.dump(tree)


def test_a_pass_with_nothing_to_do_says_so(monkeypatch):
    """Invariant 15. An empty pass is not an empty success."""
    monkeypatch.setattr(R, "_probe", lambda backend: None)
    out = R.L2_retype_v3(complete=_fake(_reply()))
    assert out["typed"] == 0
    assert "NOTHING TO DO" in out["verdict"]


def test_rows_are_appended_with_vocabulary_version_3(monkeypatch, tmp_path):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    out = R.L2_retype_v3(complete=_fake(_reply(
        entities={"incumbent": "Micron", "entrant": "CXMT"})))
    assert out["typed"] == 1 and out["on_target_rows"] == 1
    written = [json.loads(x) for x in
               R.output_path().read_text(encoding="utf-8").splitlines()]
    assert len(written) == 1
    row = written[0]
    assert row["vocabulary_version"] == 3
    assert row["vocabulary_hash"] == vocab.VOCABULARY_HASH
    assert row["event_type"] == "foreign_entrant_capacity"
    assert row["entities"] == {"incumbent": "Micron", "entrant": "CXMT"}
    assert row["job"] == "L2_retype_v3"
    assert row["prefilter_hits"] == ["foreign_entrant_capacity"]


def test_an_off_target_answer_is_written_and_counted_apart(monkeypatch):
    """A screened-in text the reader types as something else is a RESULT: the
    screen's precision is a number, and hiding the misses would make it one."""
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    out = R.L2_retype_v3(complete=_fake(json.dumps({
        "event_type": "no_event", "direction": 0,
        "magnitude_bucket": "NEGLIGIBLE", "confidence": 0.9,
        "evidence_span": ""})))
    assert out["typed"] == 1
    assert out["on_target_rows"] == 0
    assert out["by_type"]["no_event"] == 1


def test_a_refusal_is_written_and_counted_by_class(monkeypatch):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    out = R.L2_retype_v3(complete=_fake("not json at all"))
    assert out["typed"] == 0 and out["refused"] == 1
    assert out["refusals"]["REFUSED_UNPARSEABLE"] == 1
    written = [json.loads(x) for x in
               R.output_path().read_text(encoding="utf-8").splitlines()]
    assert written[0]["reason"] == "REFUSED_UNPARSEABLE"
    assert written[0]["vocabulary_version"] == 3


def test_the_receipt_refuses_to_offer_a_rate(monkeypatch):
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    out = R.L2_retype_v3(complete=_fake(_reply()))
    assert "the denominator is the SCREEN" in out["on_target_share_is_not_quotable"]
    assert out["prefilter"]["prefilter_sha256"]
    assert out["vocabulary"]["previous_hash"] == vocab.VOCABULARY_HASH_V2
    json.dumps(out, default=str)


def test_the_job_costs_no_dollars_and_takes_no_cloud_backend():
    """A local-only job needs no dollar cap, and must not grow one by accident:
    a metered backend here would spend without a cap in force."""
    import inspect
    src = inspect.getsource(R)
    assert "deepseek" not in src.lower()
    assert "max_usd" not in src
    assert R.L2_retype_v3.__kwdefaults__["backend"] == ex.BACKEND == "local_gguf"


# --------------------------------------------------------------------------
# 6. registration


def test_the_job_is_registered_with_a_stage():
    from scripts.night_factory_jobs import JOBS, JOB_STAGES
    assert "L2_retype_v3" in JOBS
    assert JOB_STAGES["L2_retype_v3"] == "features"


def test_it_sits_in_the_idle_queue_right_after_the_backlog_job():
    from backend import config as _config
    q = [j for j, _ in _config.LAB_IDLE_QUEUE]
    assert q[0] == "L2_typed_events"
    assert q[1] == "L2_retype_v3"
    box = dict(_config.LAB_IDLE_QUEUE)["L2_retype_v3"]
    assert box == 60


def test_the_run_date_is_never_a_literal():
    """The AST test over LAB_IDLE_QUEUE checks this too; asserted here as well
    so the failure names THIS file rather than the queue."""
    tree = ast.parse(Path(R.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "RUN_DATE"
                for t in node.targets):
            assert not isinstance(node.value, ast.Constant)


def test_the_lab_queues_AST_guard_still_passes_with_this_job_in_it():
    from backend.tests import test_always_on_lab as T
    T.test_no_queued_job_writes_to_a_literal_night_folder()


def test_document_date_is_never_empty_for_a_candidate(monkeypatch):
    """`user_prompt` REFUSES an undated document: a model asked to classify one
    dates it from its own training, which is the lookahead L3 measures."""
    rows = [_corpus_row("a", "CXMT passes AM5 qualification")]
    monkeypatch.setattr(R, "read_rows", lambda files: (rows, []))
    for u in R.candidate_units()["units"]:
        assert u["document_date"]
        ex.user_prompt(scope=u["scope"], scope_kind=u["scope_kind"],
                       document_date=u["document_date"],
                       source_feed=u["source_feed"], title=u["title"],
                       body=u["body"])


def test_the_output_name_moves_with_the_run_date():
    """Unset, RUN_DATE is TODAY; `NIGHT_RUN_DATE` reproduces a past night. An
    output path that did not carry it would overwrite a committed receipt,
    which is exactly what three idle-queue jobs did on 2026-09-18."""
    assert R.RUN_DATE in str(R.output_path())
    assert R.RUN_DATE in (date.today().isoformat(),
                          __import__("os").getenv("NIGHT_RUN_DATE"))
