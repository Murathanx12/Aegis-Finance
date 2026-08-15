"""The collection receipt must carry everything, because the day does not repeat.

WHY THIS IS PINNED
==================
`pi_ownership_collect`'s first production run is the only invocation that can
prove Railway's egress reaches EDGAR at all — this project has already shipped a
collector that passed twelve offline tests while 403-ing on 100% of its
production fetches (T9). A receipt that omits a field cannot be enriched
afterwards; the day is gone and the next one is a different day.

So the required fields are asserted here rather than hoped for, and the one that
matters most is the pair `n_attempted` / `n_documents_fetched`. A collector that
attempted 512 documents and fetched 0 is the T9 shape exactly, and a receipt
carrying only "attempted" cannot express it.
"""

from __future__ import annotations

#: Everything the 2026-08-15 order requires to be answerable from the receipt.
REQUIRED = (
    "day", "source_status",
    "n_index_rows", "n_unique_accessions", "n_attempted",
    "n_documents_fetched", "coverage", "n_parse_errors", "failure_classes",
    "events_by_action", "n_buys", "n_sells", "n_mechanical",
    "n_distinct_actors", "n_distinct_tickers",
    "fetch_seconds", "total_seconds",
    "written", "duplicates", "usable_events",
)


def _payload(**over):
    p = {
        "date": "2026-08-14", "status": "OK_DATA", "n_index_rows": 1098,
        "n_ownership_filings_in_index": 512, "n_unique_accessions": 512,
        "n_joint_filing_rows_collapsed": 586, "n_attempted": 512,
        "n_documents_fetched": 510, "sampled": False, "coverage": 1.0,
        "n_parsed": 508, "n_parse_errors": 4,
        "failure_classes": {"document_not_retrievable": 2, "bad_xml": 2},
        "parsed": [],
    }
    p.update(over)
    return p


def test_every_required_field_is_on_the_receipt(monkeypatch, tmp_path):
    from backend.services.teacher_library import adapters_ownership as AO

    # `collect=` is a real seam. The first draft patched
    # `OwnershipFormsAdapter._collect`, which is an INSTANCE attribute assigned
    # in __init__ — so the class patch silently created a new attribute, the
    # live SEC fetch ran anyway, and this test PASSED on a NOT_YET_PUBLISHED
    # response.
    res = AO.collect_and_append("2026-08-14", path=tmp_path / "events.jsonl",
                                collect=lambda subject, **kw: _payload())

    missing = [k for k in REQUIRED if k not in res]
    assert not missing, (
        f"the collection receipt omits {missing}. The first production run "
        f"cannot be re-run, so a field absent here is a question that can "
        f"never be answered about that day")


def test_attempted_and_fetched_are_separate_numbers(monkeypatch, tmp_path):
    """The T9 shape has to be expressible, or it cannot be detected.

    A collector 403-ing on every request still 'attempts' the whole day. If the
    receipt carries only `n_attempted`, a total outage and a perfect run look
    identical on it.
    """
    from backend.services.teacher_library import adapters_ownership as AO

    res = AO.collect_and_append(
        "2026-08-14", path=tmp_path / "e.jsonl",
        collect=lambda subject, **kw: _payload(n_documents_fetched=0,
                                               n_parse_errors=512))

    assert res["n_attempted"] == 512
    assert res["n_documents_fetched"] == 0


def test_failure_classes_are_a_breakdown_not_a_count(monkeypatch, tmp_path):
    """"12 failures" cannot distinguish a rate limit from a schema change."""
    from backend.services.teacher_library import adapters_ownership as AO

    res = AO.collect_and_append("2026-08-14", path=tmp_path / "e.jsonl",
                                collect=lambda subject, **kw: _payload())
    assert res["failure_classes"] == {"document_not_retrievable": 2,
                                      "bad_xml": 2}


def test_a_day_edgar_has_not_published_still_produces_the_same_key_set(
        monkeypatch, tmp_path):
    """A receipt whose shape depends on the outcome forces the reader to know
    the outcome before they can read it."""
    from backend.services.teacher_library import adapters_ownership as AO

    res = AO.collect_and_append(
        "2026-08-14", path=tmp_path / "e.jsonl",
        collect=lambda subject, **kw: {"date": "2026-08-14",
                                       "status": "NOT_YET_PUBLISHED",
                                       "reason": "index not posted",
                                       "parsed": []})
    missing = [k for k in REQUIRED if k not in res]
    assert not missing, missing
    assert res["source_status"] == "NOT_YET_PUBLISHED"


def test_sells_and_mechanical_events_are_counted_not_only_buys(monkeypatch,
                                                               tmp_path):
    """The pre-2026-08 path kept purchases. A library of successful-looking buy
    stories is what that produces, and the counts are how it stays visible."""
    from backend.services.teacher_library import adapters_ownership as AO
    from backend.services.teacher_library import events as E

    class _Ev:
        usable = True

        def __init__(self, action, actor, ticker):
            self.action_type, self.actor_id = action, actor
            self.ticker_at_event = ticker

    monkeypatch.setattr(
        AO.OwnershipFormsAdapter, "to_events",
        lambda self, payload: [_Ev("SELL", "a", "AAA"), _Ev("SELL", "b", "BBB"),
                               _Ev("BUY", "a", "AAA"), _Ev("OTHER", "c", "CCC")])
    res = AO.collect_and_append(
        "2026-08-14", path=tmp_path / "e.jsonl",
        collect=lambda subject, **kw: _payload(),
        append_fn=lambda produced, path=None: {"written": len(produced),
                                               "duplicates": 0})

    assert res["n_sells"] == 2
    assert res["n_buys"] == 1
    assert res["n_mechanical"] == 1
    assert res["events_by_action"] == {"SELL": 2, "BUY": 1, "OTHER": 1}
    assert res["n_distinct_actors"] == 3
    assert res["n_distinct_tickers"] == 3
    assert E is not None
