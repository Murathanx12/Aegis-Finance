"""The L2 extraction contract: the prompt, the schema, the refusals, the golden set.

The model is MOCKED everywhere in this file. What is being pinned is the
CONTRACT -- that the prompt is the spec's prompt, that a reply outside the enum
is refused rather than passed through, that a refusal keeps its class and its
raw text, and that the 23 spec rows round-trip to exactly the JSON the spec
wrote down. A test that needed the local model would be skipped on every machine
that has not started it, and a check that did not run is not a check that passed.
"""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from backend.services import event_extraction as ex
from backend.services import event_vocabulary as vocab
from backend.services import llm_language as _lang

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "research_notes" / "2026-09-11" / "spec_events_and_calibration.md"
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "events" / "golden.jsonl"


def _golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def _spec_block(header: str, nxt: str) -> str:
    text = SPEC.read_text(encoding="utf-8")
    return text[text.index(header):text.index(nxt)]


# ------------------------------------------------------------------- the prompt

def test_the_wire_system_prompt_is_the_specs_prompt_verbatim():
    """Including the pin: the spec's rule 9 ends with `LANGUAGE_PIN`, which
    `wire_system()` reconstructs by calling `llm_language.pin`."""
    block = _spec_block("### 2.2 System prompt (verbatim)", "### 2.3")
    spec_text = block.split("```")[1].strip("\n")
    assert ex.wire_system("A").strip() == spec_text.strip()


def test_the_module_does_not_pin_the_language_at_this_call_site():
    """AST, not grep: the docstring explains the pin at length, and a grep-shaped
    guard that cannot tell an explanation from an instance is a broken guard."""
    tree = ast.parse(Path(ex.__file__).read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute) else
                    fn.id if isinstance(fn, ast.Name) else "")
            if name == "pin":
                parent = None
                for fdef in ast.walk(tree):
                    if isinstance(fdef, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                            any(n is node for n in ast.walk(fdef)):
                        parent = fdef.name
                calls.append(parent)
    # exactly one `pin()` call, and it is the display/hash helper -- never the
    # path that reaches `complete()`
    assert calls == ["wire_system"], calls


def test_the_user_template_is_the_specs_template():
    block = _spec_block("### 2.3 User template", "### 2.4")
    spec_text = block.split("```")[1].strip("\n")
    # the spec's template carries two HTML comments as annotations for the reader
    stripped = "\n".join(line.split("<!--")[0].rstrip() for line in spec_text.splitlines())
    mine = ex.USER_TEMPLATE.replace("{scope_kind}", '{"ticker" if company else "macro_topic"}')
    mine = mine.replace("{document_date}", "{document_date_iso}")
    mine = mine.replace("{body}", "{body_text_truncated_to_2000_chars}")
    assert mine.strip() == stripped.strip()


def test_a_document_with_no_date_is_refused_not_rendered():
    with pytest.raises(ValueError) as exc:
        ex.user_prompt(scope="ACME", scope_kind="ticker", document_date="",
                       source_feed="f", title="t")
    assert "PIT anchor" in str(exc.value)


def test_the_body_is_truncated_at_the_specs_ceiling():
    prompt = ex.user_prompt(scope="ACME", scope_kind="ticker",
                            document_date=date.today().isoformat(),
                            source_feed="f", title="t", body="x" * 5000)
    assert prompt.count("x") == ex.BODY_CHARS == 2000


def test_the_two_prompts_carry_the_same_contract_and_different_hashes():
    """The inter-rater control needs a SECOND prompt, not a second contract: a
    kappa between two prompts that ask different things measures nothing."""
    assert ex.PROMPT_HASH != ex.PROMPT_HASH_B
    for prompt in (ex.SYSTEM_PROMPT, ex.SYSTEM_PROMPT_B):
        low = prompt.lower()
        assert "no_event" in low
        assert "-1, 0" in low or "-1, 0 or +1" in low
        assert "fourth value" in low
        assert "negligible" in low and "extreme" in low
        assert "verbatim" in low
        assert "denial" in low and "recap" in low
        assert "fences" in low


def test_the_prompt_hash_moves_when_the_schema_moves(monkeypatch):
    before = ex.prompt_hash("A")
    monkeypatch.setitem(ex.SCHEMA["properties"]["confidence"], "maximum", 2.0)
    assert ex.prompt_hash("A") != before


# ------------------------------------------------------------------- the schema

def test_the_schema_enum_is_the_vocabulary_and_is_not_retyped():
    assert ex.SCHEMA["properties"]["event_type"]["enum"] == list(vocab.EVENT_TYPES)
    assert ex.SCHEMA["properties"]["direction"]["enum"] == [-1, 0, 1]
    assert ex.SCHEMA["additionalProperties"] is False
    spec_block = _spec_block("### 2.1 JSON Schema", "### 2.2")
    spec_schema = json.loads(spec_block.split("```json")[1].split("```")[0])
    assert spec_schema == ex.SCHEMA


def test_the_hand_validator_is_the_one_that_runs_here():
    """`jsonschema` is not installed in this environment. A guard on a dormant
    branch protects nothing, so the live path is the tested path."""
    assert ex.validator_in_use() in ("hand", "jsonschema")
    try:
        import jsonschema                                        # noqa: F401
    except ImportError:
        assert ex.validator_in_use() == "hand"


@pytest.mark.parametrize("bad,needle", [
    ({"event_type": "analyst_rating", "direction": 1, "magnitude_bucket": "SMALL",
      "confidence": 0.5, "evidence_span": "x"}, "frozen ids"),
    ({"event_type": "earnings_report", "direction": 2, "magnitude_bucket": "SMALL",
      "confidence": 0.5, "evidence_span": "x"}, "fourth value"),
    ({"event_type": "earnings_report", "direction": 1, "magnitude_bucket": "HUGE",
      "confidence": 0.5, "evidence_span": "x"}, "magnitude_bucket"),
    ({"event_type": "earnings_report", "direction": 1, "magnitude_bucket": "SMALL",
      "confidence": 1.4, "evidence_span": "x"}, "outside [0, 1]"),
    ({"event_type": "earnings_report", "direction": 1, "magnitude_bucket": "SMALL",
      "confidence": 0.5, "evidence_span": "x", "rationale": "because"}, "additionalProperties"),
    ({"event_type": "earnings_report", "direction": 1, "magnitude_bucket": "SMALL",
      "confidence": 0.5}, "required and missing"),
    ({"event_type": "earnings_report", "direction": 1, "magnitude_bucket": "SMALL",
      "confidence": 0.5, "evidence_span": "y" * 401}, "ceiling"),
])
def test_every_way_a_row_can_be_wrong_is_a_schema_refusal(bad, needle):
    errs = ex.schema_errors(bad)
    assert errs, bad
    assert any(needle in e for e in errs), errs
    out = ex.parse_reply(json.dumps(bad))
    assert isinstance(out, ex.Refusal) and out.reason == "REFUSED_SCHEMA"
    assert out.raw, "a refused reply must keep its raw text for the regression corpus"


def test_a_boolean_is_not_an_integer_direction():
    errs = ex.schema_errors({"event_type": "no_event", "direction": True,
                             "magnitude_bucket": "NEGLIGIBLE", "confidence": 0.5,
                             "evidence_span": ""})
    assert any("direction" in e for e in errs)


# ------------------------------------------------------------------ the refusals

def test_a_non_latin_reply_is_refused_before_it_is_parsed():
    """Order matters: valid JSON in the wrong language is still not the answer
    that was asked for, and parsing it first would record it as a success."""
    before = dict(_lang.refusals())
    reply = json.dumps({"event_type": "earnings_report", "direction": 1,
                        "magnitude_bucket": "MODERATE", "confidence": 0.9,
                        "evidence_span": "公司报告了季度业绩"
                                         "超出预期的利润"},
                       ensure_ascii=False)
    out = ex.parse_reply(reply, provider="test_provider")
    assert isinstance(out, ex.Refusal) and out.reason == "REFUSED_LANGUAGE"
    assert "not repaired" in out.detail
    assert _lang.refusals().get("test_provider", 0) == before.get("test_provider", 0) + 1


def test_an_unparseable_reply_keeps_its_raw_text_capped():
    out = ex.parse_reply("Sure! Here is the classification: it's an earnings beat." * 60)
    assert isinstance(out, ex.Refusal) and out.reason == "REFUSED_UNPARSEABLE"
    assert len(out.raw) == ex.RAW_KEEP


def test_an_empty_reply_is_unparseable_not_a_no_event():
    out = ex.parse_reply("   ")
    assert isinstance(out, ex.Refusal) and out.reason == "REFUSED_UNPARSEABLE"


def test_markdown_fences_are_stripped_and_nothing_else_is_repaired():
    payload = {"event_type": "no_event", "direction": 0,
               "magnitude_bucket": "NEGLIGIBLE", "confidence": 0.7, "evidence_span": ""}
    out = ex.parse_reply("```json\n" + json.dumps(payload) + "\n```")
    assert isinstance(out, ex.TypedEventRow) and out.event_type == "no_event"
    # a trailing comma is NOT repaired
    assert isinstance(ex.parse_reply('{"event_type": "no_event",}'), ex.Refusal)


def test_no_event_is_a_successful_row_and_never_a_refusal():
    """It is how L2 measures the corpus's genuine event rate; discarding it makes
    the denominator silently wrong."""
    assert "no_event" not in ex.REFUSAL_CLASSES
    row = ex.parse_reply(json.dumps(
        {"event_type": "no_event", "direction": 0, "magnitude_bucket": "NEGLIGIBLE",
         "confidence": 0.7, "evidence_span": ""}))
    assert isinstance(row, ex.TypedEventRow)


# --------------------------------------------------------------- provenance

def test_a_typed_row_carries_the_vocabulary_VERSION_beside_the_hash():
    """A hash says WHICH table; a version says which table a reader should go
    looking for. A corpus typed across a vocabulary change needs both."""
    row, _ = ex.extract(scope="ACME", scope_kind="ticker",
                        document_date=date.today().isoformat(), source_feed="f",
                        title="Goldman upgrades Acme to Buy",
                        complete=lambda *a, **kw: _fake_reply(json.dumps(
                            {"event_type": "analyst_rating_change", "direction": 1,
                             "magnitude_bucket": "MODERATE", "confidence": 0.8,
                             "evidence_span": "Goldman upgrades Acme to Buy"})))
    assert isinstance(row, ex.TypedEventRow)
    assert row.vocabulary_version == vocab.VOCABULARY_VERSION == 2
    assert row.as_dict()["vocabulary_version"] == 2


def test_every_typed_row_carries_the_prompt_and_vocabulary_hashes():
    payload = {"event_type": "stock_buyback", "direction": 1,
               "magnitude_bucket": "SMALL", "confidence": 0.85,
               "evidence_span": "board authorizes"}
    row = ex.parse_reply(json.dumps(payload),
                         document="Acme board authorizes new $1B share buyback program")
    assert row.prompt_hash == ex.PROMPT_HASH
    assert row.vocabulary_hash == vocab.VOCABULARY_HASH
    assert row.evidence_span_verbatim is True
    b = ex.parse_reply(json.dumps(payload), variant="B")
    assert b.prompt_hash == ex.PROMPT_HASH_B != ex.PROMPT_HASH


def test_a_paraphrased_span_is_measured_not_refused():
    payload = {"event_type": "stock_buyback", "direction": 1,
               "magnitude_bucket": "SMALL", "confidence": 0.85,
               "evidence_span": "the board approved a buyback"}
    row = ex.parse_reply(json.dumps(payload), document="Acme authorizes $1B repurchase")
    assert isinstance(row, ex.TypedEventRow)
    assert row.evidence_span_verbatim is False


# ------------------------------------------------------------------ the call

def _fake_reply(text: str):
    class R:
        def __init__(self):
            self.text = text
            self.tokens_in, self.tokens_out = 300, 60
            self.cost_usd, self.latency_s = 0.0, 1.5
    return R()


def test_extract_sends_the_unpinned_prompt_and_returns_a_typed_row():
    seen = {}

    def fake_complete(backend, prompt, *, system, max_tokens, temperature, purpose):
        seen.update(backend=backend, prompt=prompt, system=system, purpose=purpose)
        return _fake_reply(json.dumps(
            {"event_type": "guidance_change", "direction": 1,
             "magnitude_bucket": "MODERATE", "confidence": 0.85,
             "evidence_span": "raises full-year guidance"}))

    row, usage = ex.extract(scope="ACME", scope_kind="ticker",
                            document_date=date.today().isoformat(),
                            source_feed="alpaca_benzinga_news",
                            title="Acme raises full-year guidance on strong cloud demand",
                            complete=fake_complete)
    assert isinstance(row, ex.TypedEventRow) and row.event_type == "guidance_change"
    assert usage["cost_usd"] == 0.0 and usage["tokens_out"] == 60
    assert seen["backend"] == "local_gguf" and seen["purpose"] == ex.PURPOSE
    # the pin is the wire's job -- it must NOT be in what this module sends
    assert not seen["system"].endswith(_lang.LANGUAGE_PIN)
    assert seen["system"] == ex.SYSTEM_PROMPT


def test_a_language_refusal_from_the_wire_becomes_a_row_level_refusal():
    from backend.services.model_provider import LanguageRefused

    def fake_complete(*a, **kw):
        raise LanguageRefused("83% non-Latin script", reply=_fake_reply("中文"),
                              share=0.83)

    row, usage = ex.extract(scope="ACME", scope_kind="ticker",
                            document_date=date.today().isoformat(),
                            source_feed="f", title="t", complete=fake_complete)
    assert isinstance(row, ex.Refusal) and row.reason == "REFUSED_LANGUAGE"
    assert usage["cost_usd"] == 0.0


def test_a_provider_refusal_is_not_caught_here():
    """The server being down is not a property of the document. The night job
    probes first and refuses by name; swallowing it here would turn 6,000
    impossible calls into 6,000 refusal rows."""
    from backend.services.model_provider import ProviderRefusal

    def fake_complete(*a, **kw):
        raise ProviderRefusal("nothing is listening on 127.0.0.1:8080")

    with pytest.raises(ProviderRefusal):
        ex.extract(scope="ACME", scope_kind="ticker",
                   document_date=date.today().isoformat(),
                   source_feed="f", title="t", complete=fake_complete)


# ------------------------------------------------------------------ golden set

def test_the_fixture_is_the_specs_own_26_rows():
    """Derived from the spec's sections 2.6, 2.7 and 2.8, not eyeballed."""
    import re

    block = _spec_block("### 2.6 Golden set",
                        "A regression test (`test_event_vocabulary_golden_set.py`")
    parsed = {}
    for line in block.splitlines():
        m = re.match(r"^(\d+)\.\s+(.*?)\s*$", line)
        if not m:
            continue
        hm = re.search(r'"([^"]+)"\s*(?:\(source hint\))?\s*→\s*`\{([^}]*)\}`', m.group(2))
        assert hm, m.group(1)
        fields = [f.strip() for f in hm.group(2).split(",")]
        if ":" in fields[0]:
            d = dict(f.split(":", 1) for f in fields)
            d = {k.strip(): v.strip() for k, v in d.items()}
        else:
            d = dict(zip(("event_type", "direction", "magnitude_bucket", "confidence"), fields))
        parsed[int(m.group(1))] = (hm.group(1), d)
    assert len(parsed) == 26

    rows = _golden()
    assert len(rows) == 26
    assert [r["id"] for r in rows] == list(range(1, 27))
    assert sum(1 for r in rows if r["spec_section"] == "2.7") == 3
    assert sum(1 for r in rows if r["spec_section"] == "2.8") == 3
    for r in rows:
        headline, d = parsed[r["id"]]
        assert r["title"] == headline
        assert r["expected"]["event_type"] == d["event_type"]
        assert r["expected"]["direction"] == int(d["direction"])
        assert r["expected"]["magnitude_bucket"] == d["magnitude_bucket"]
        assert r["expected"]["confidence"] == float(d["confidence"])


def test_every_golden_row_round_trips_through_the_parser_with_a_mocked_model():
    """THE PIN: for each of the 23 rows, a model that answers the spec's own JSON
    produces exactly the spec's typed row -- every field, not just the type."""
    today = date.today().isoformat()
    for r in _golden():
        expected = r["expected"]

        def fake_complete(backend, prompt, *, system, max_tokens, temperature, purpose,
                          _e=expected):
            assert r["title"] in prompt and r["scope"] in prompt
            return _fake_reply(json.dumps(_e))

        row, _ = ex.extract(scope=r["scope"], scope_kind=r["scope_kind"],
                            document_date=today, source_feed=r["source_feed"],
                            title=r["title"], body=r["body"], complete=fake_complete)
        assert isinstance(row, ex.TypedEventRow), (r["id"], row)
        assert row.event_type == expected["event_type"], r["id"]
        assert row.direction == expected["direction"], r["id"]
        assert row.magnitude_bucket == expected["magnitude_bucket"], r["id"]
        assert row.confidence == expected["confidence"], r["id"]
        assert row.evidence_span == expected["evidence_span"], r["id"]
        assert row.evidence_span_verbatim is True, r["id"]
        assert row.vocabulary_hash == vocab.VOCABULARY_HASH
        assert row.vocabulary_version == vocab.VOCABULARY_VERSION


def test_the_three_v2_rows_cover_the_analyst_family_including_a_neutral_one():
    """Row 26 earns its place: a neutral initiation is a REAL, dated event with
    no directional implication by itself, which is what `direction: 0` means --
    and it is what a keyword match on "initiates coverage" gets wrong in both
    directions."""
    rows = {r["id"]: r for r in _golden()}
    assert rows[24]["expected"]["event_type"] == "analyst_rating_change"
    assert rows[24]["expected"]["direction"] == 1
    assert rows[25]["expected"]["event_type"] == "analyst_target_change"
    assert rows[25]["expected"]["direction"] == -1
    assert rows[26]["expected"]["event_type"] == "analyst_initiation"
    assert rows[26]["expected"]["direction"] == 0


def test_the_three_adversarial_rows_say_what_the_spec_says_they_say():
    rows = {r["id"]: r for r in _golden()}
    # 21 sarcasm: the tone does not change the type
    assert rows[21]["expected"]["event_type"] == "management_change_departure"
    assert rows[21]["expected"]["direction"] == -1
    # 22 denial: NOT positive (the naive keyword read) and NOT no_event
    assert rows[22]["expected"]["event_type"] == "mergers_acquisitions"
    assert rows[22]["expected"]["direction"] == -1
    # 23 recap: no_event, and specifically not a second mergers_acquisitions row
    assert rows[23]["expected"]["event_type"] == "no_event"
    assert rows[23]["expected"]["direction"] == 0


def test_every_golden_expectation_is_itself_schema_valid():
    for r in _golden():
        assert ex.schema_errors(r["expected"]) == [], r["id"]


def test_the_declaration_names_the_validator_and_both_prompt_hashes():
    d = ex.declaration()
    assert d["prompt_hash_A"] == ex.PROMPT_HASH and d["prompt_hash_B"] == ex.PROMPT_HASH_B
    assert d["validator"] == ex.validator_in_use()
    assert d["vocabulary"]["vocabulary_hash"] == vocab.VOCABULARY_HASH
    assert "CENTRALLY" in d["language_pin"]
