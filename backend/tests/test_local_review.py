"""The review pass emits ROWS, and a document it cannot answer emits a REFUSAL row.

THE ONE THING THIS BATTERY EXISTS TO CATCH
==========================================
A model produces a fluent answer for every document, including the ones with no
answer in them. So the known-answer set contains NULLS -- a weather forecast and
a recipe -- and a run that extracts an event from either has invented it. A
battery with no null in it cannot tell a working extractor from a confident one,
which is the same reason every mechanism in this repo carries a matched control.

The LIVE battery (real models, real latency) is `scripts/local_review_run.py
--known-answer` and its receipts are in
`backend/data/optimus/free_inference_2026-09-07/`. These tests are the offline
half: the parse, the schema, the refusal branches and the cost arithmetic, with
the model stubbed. NO NETWORK.
"""

from __future__ import annotations

import pytest

from backend.config import LLM_PRICE_PER_MTOK
from backend.services import free_inference as fi
from backend.services import local_review as lr
from backend.services.model_provider import LanguageRefused, ProviderRefusal, Reply

GOOD = ('{"event_type": "EARNINGS", "entity": "Zhongtai Semiconductor", '
        '"direction": "POSITIVE", "horizon_days": 30, "confidence": 0.9, '
        '"evidence_quote": "revenue rose 34%"}')


def _stub(text: str, *, tin: int = 100, tout: int = 40):
    def _f(backend=None, prompt="", **kw):
        return fi.FreeReply(backend=backend or "local_gguf", model="local",
                            text=text, latency_s=0.01, tokens_in=tin,
                            tokens_out=tout, cost_usd=0.0, cost_class="free")
    return _f


# ── the happy path ──────────────────────────────────────────────────────────
def test_a_good_reply_becomes_a_typed_row(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub(GOOD))
    row = lr.review_one("d1", "some earnings text")
    assert row.status == "OK" and not row.is_refusal
    assert row.event_type == "EARNINGS"
    assert row.entity == "Zhongtai Semiconductor"
    assert row.direction == "POSITIVE"
    assert row.horizon_days == 30
    assert row.confidence == 0.9
    assert row.tokens_in == 100 and row.cost_usd == 0.0


def test_a_fenced_reply_with_a_preamble_still_parses(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub(
        "Sure! Here is the record:\n```json\n" + GOOD + "\n```\nHope that helps."))
    assert lr.review_one("d1", "text").status == "OK"


# ── THE NULLS: every refusal is a ROW ───────────────────────────────────────
def test_a_planted_null_comes_back_as_a_refusal_not_an_invention(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub('{"event_type": "NO_EVENT"}'))
    row = lr.review_one("null1", "A band of heavy rain will move across...")
    assert row.status == "REFUSED_NO_EVENT"
    assert row.is_refusal
    assert row.entity is None and row.confidence is None
    assert "no company-level event" in row.refusal_reason


def test_an_unparseable_reply_is_a_row_and_not_a_dropped_document(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub("I think this is about earnings."))
    row = lr.review_one("d1", "text")
    assert row.status == "REFUSED_UNPARSEABLE"
    assert row.refusal_reason and "earnings" in row.refusal_reason


def test_valid_json_that_is_not_this_schema_is_refused_whole(monkeypatch):
    """Never partially accept: a half-valid row is how a column ends up with
    three types and a group-by silently reports on a subset."""
    monkeypatch.setattr(fi, "complete", _stub('{"event_type": "VIBES_SHIFT"}'))
    row = lr.review_one("d1", "text")
    assert row.status == "REFUSED_SCHEMA"
    assert row.entity is None and row.direction is None


def test_an_empty_document_blames_the_store_and_not_the_model(monkeypatch):
    called = []
    monkeypatch.setattr(fi, "complete", lambda *a, **k: called.append(1))
    row = lr.review_one("d1", "   ")
    assert row.status == "REFUSED_EMPTY_DOC"
    assert not called, "an empty document must not be sent to a model"
    assert "not a model failure" in row.refusal_reason


def test_a_provider_failure_is_a_row_and_never_an_exception(monkeypatch):
    def _boom(*a, **k):
        raise ProviderRefusal("nvidia HTTP 429: Too Many Requests")
    monkeypatch.setattr(fi, "complete", _boom)
    row = lr.review_one("d1", "text")
    assert row.status == "REFUSED_PROVIDER" and "429" in row.refusal_reason


def test_a_language_refusal_keeps_the_tokens_it_burned(monkeypatch):
    """Discarded is not free. A refusal that loses its token count turns the
    refusal RATE into a number with no denominator."""
    def _boom(*a, **k):
        raise LanguageRefused(
            "non-Latin", reply=Reply(provider="p", model="m", text="股票",
                                     latency_s=0.1, prompt_tokens=80,
                                     completion_tokens=12), share=1.0)
    monkeypatch.setattr(fi, "complete", _boom)
    row = lr.review_one("d1", "text")
    assert row.status == "REFUSED_LANGUAGE"
    assert (row.tokens_in, row.tokens_out) == (80, 12)


def test_every_declared_refusal_status_is_reachable():
    """A status nothing can produce is a status that lies about the taxonomy."""
    produced = {"REFUSED_NO_EVENT", "REFUSED_UNPARSEABLE", "REFUSED_SCHEMA",
                "REFUSED_LANGUAGE", "REFUSED_PROVIDER", "REFUSED_EMPTY_DOC"}
    assert set(lr.REFUSALS) == produced


# ── clamping ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,want", [(0, None), (-5, 1), (9999, 250), (63, 63)])
def test_horizon_is_clamped_rather_than_trusted(raw, want):
    obj = {"event_type": "EARNINGS", "horizon_days": raw, "confidence": 0.5}
    fields, refusal = lr.validate(obj)
    assert refusal is None and fields["horizon_days"] == want


def test_confidence_out_of_range_is_clamped_not_refused():
    fields, _ = lr.validate({"event_type": "EARNINGS", "confidence": 7.4})
    assert fields["confidence"] == 1.0


def test_an_unknown_direction_degrades_to_UNCLEAR():
    fields, _ = lr.validate({"event_type": "EARNINGS", "direction": "SIDEWAYS"})
    assert fields["direction"] == "UNCLEAR"


# ── the receipt ─────────────────────────────────────────────────────────────
def test_the_batch_receipt_reports_zero_dollars_AND_the_counterfactual(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub(GOOD, tin=1000, tout=500))
    rows, rec = lr.review_batch([(f"d{i}", "text") for i in range(4)])
    assert rec["n_docs"] == 4 and rec["n_ok"] == 4
    assert rec["cost_usd"] == 0.0 and rec["cost_usd_str"] == "$0.00"
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    # `round(..., 6)` in the receipt is deliberate: a spend line quoted to the
    # nanodollar reads as a precision the price table does not have. So the
    # assertion is made at the receipt's own resolution.
    want = round((4000 * p["in"] + 2000 * p["out"]) / 1e6, 6)
    assert rec["deepseek_counterfactual_usd"] == pytest.approx(want, abs=5e-7)
    assert rec["saved_usd"] > 0
    assert rec["docs_per_hour"] > 0 and rec["wall_clock_s"] >= 0


def test_the_batch_writes_rows_INCREMENTALLY(monkeypatch):
    """The scrape store's lesson applied to compute: a receipt that only exists
    at the end does not exist for any run that fails."""
    monkeypatch.setattr(fi, "complete", _stub(GOOD))
    seen = []
    lr.review_batch([(f"d{i}", "t") for i in range(3)], on_row=seen.append)
    assert len(seen) == 3 and all(r.status == "OK" for r in seen)


def test_refusals_are_counted_in_the_receipt_not_dropped(monkeypatch):
    monkeypatch.setattr(fi, "complete", _stub('{"event_type": "NO_EVENT"}'))
    _, rec = lr.review_batch([("a", "t"), ("b", "t")])
    assert rec["n_docs"] == 2 and rec["n_ok"] == 0 and rec["n_refusals"] == 2
    assert rec["by_status"] == {"REFUSED_NO_EVENT": 2}


# ── canon ───────────────────────────────────────────────────────────────────
def test_no_row_field_can_be_read_as_a_size_a_stop_or_a_price():
    """`CLAUDE.md`: no LLM output reaches a size, a stop or an order. Enforcing
    it as a NAME check is crude and it is checkable, which a sentence is not."""
    banned = ("weight", "size", "qty", "quantity", "shares", "notional",
              "stop", "target_price", "limit_price", "order", "allocation")
    fields = set(lr.ReviewRow.__dataclass_fields__)
    assert not {f for f in fields if any(b in f for b in banned)}


def test_the_vocabulary_is_closed_and_contains_its_own_escape():
    assert "NO_EVENT" in lr.EVENT_TYPES, (
        "without an explicit escape the model must label every document, which "
        "is the condition under which it invents")
    assert "NO_EVENT" in lr._SYSTEM and "verbatim" in lr._SYSTEM
