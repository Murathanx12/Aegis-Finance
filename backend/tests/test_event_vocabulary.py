"""The L2 vocabulary is the spec's own table, and the hash is a content hash.

Two failures this file exists to make loud:

1. The module and `spec_events_and_calibration.md` section 1.2 drifting apart.
   Every row is re-parsed from the markdown on every run, so an edit to either
   side that does not reach the other is red here, not a discovery six weeks
   later when a receipt quotes a definition nobody can find.
2. `VOCABULARY_HASH` moving for a reason that is not a content change. It is
   stamped into every typed row L2 writes; a hash that moves when a dataclass
   field is reordered would retire a corpus for nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.services import event_vocabulary as ev
from backend.services import scenario_forecasts as sf

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "research_notes" / "2026-09-11" / "spec_events_and_calibration.md"


def _spec_rows() -> list[tuple[str, ...]]:
    """Section 1.2's table, one tuple per row, parsed not transcribed."""
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 1.2 The frozen vocabulary"):
                   text.index("That is 38 substantive")]
    rows = []
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|(.*)\|\s*$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        assert len(cells) == 6, f"{m.group(1)}: {len(cells)} cells, expected 6"
        rows.append((m.group(1), *cells))
    return rows


def test_every_row_is_the_specs_row():
    spec_rows = _spec_rows()
    assert len(spec_rows) == len(ev.VOCABULARY)
    for (sid, definition, sec_items, prior, magnitude, example, counter), got in zip(
            spec_rows, ev.VOCABULARY):
        assert got.id == sid
        assert got.definition == definition
        assert got.sec_items_text == sec_items
        assert got.direction_prior_text == prior
        assert got.magnitude_bucket == magnitude
        assert got.example == example
        assert got.counter_example == counter


def test_the_count_is_derived_from_the_table_and_the_specs_prose_is_off_by_one():
    """39 substantive + `no_event` = 40. The section heading says "39 event
    types + no_event" (right); its closing sentence says "38 substantive +
    no_event = 39" (wrong). Recorded rather than silently resolved, and the
    module's counters are computed from the table so neither sentence can
    decide the number."""
    assert ev.N_TYPES == len(ev.VOCABULARY) == 40
    assert ev.N_SUBSTANTIVE == 39
    assert ev.EVENT_TYPES[-1] == ev.NO_EVENT == "no_event"
    assert len(set(ev.EVENT_TYPES)) == ev.N_TYPES, "a duplicate id in the vocabulary"
    text = SPEC.read_text(encoding="utf-8")
    assert "That is 38 substantive" in text, (
        "the spec's miscount was fixed -- update this test's record of it")


def test_the_8k_item_codes_are_parsed_out_of_the_specs_cell():
    assert ev.by_id("earnings_report").sec_items == ("2.02",)
    assert ev.by_id("earnings_preannouncement").sec_items == ("2.02", "7.01")
    assert ev.by_id("mergers_acquisitions").sec_items == ("1.01", "2.01")
    # "-- (Forms 3/4/13D/13F, not 8-K)": no 8-K item, and the note is kept.
    insider = ev.by_id("insider_or_institutional_ownership_change")
    assert insider.sec_items == ()
    assert "13D" in insider.sec_items_text


def test_one_8k_item_can_name_several_types():
    """2.01 is an acquisition, a divestiture and a spinoff. This index is a
    RELATION; `edgar_events`'s item -> direction map is a function, and this
    does not replace it."""
    idx = ev.items_index()
    assert set(idx["2.01"]) >= {"mergers_acquisitions", "divestiture_asset_sale", "spinoff"}
    assert all(code in ev.by_id(t).sec_items for code, ids in idx.items() for t in ids)


def test_priors_are_signs_or_none_and_ambiguous_is_never_collapsed():
    for t in ev.VOCABULARY:
        assert t.direction_prior in (-1, 0, 1, None)
        assert t.magnitude_bucket in ev.MAGNITUDE_BUCKETS
    # both two-sign rows stay ambiguous rather than being read as their first word
    assert ev.by_id("mergers_acquisitions").direction_prior is None
    assert ev.by_id("index_rebalance").direction_prior is None
    assert ev.by_id("bankruptcy_or_going_concern").direction_prior == -1
    assert ev.by_id("stock_buyback").direction_prior == 1
    assert ev.by_id("regular_dividend_declaration").direction_prior == 0
    assert ev.by_id("no_event").direction_prior == 0


def test_the_hash_is_stable_across_key_order():
    """A content hash, not a serialisation hash: reordering the keys of every
    row must not move it."""
    rows = ev.table()
    shuffled = [{k: r[k] for k in reversed(list(r))} for r in rows]
    # dict equality ignores order, so the check that the reordering HAPPENED has
    # to be on the key sequence itself
    assert list(shuffled[0]) == list(reversed(list(rows[0]))) != list(rows[0])
    assert ev.vocabulary_hash(shuffled) == ev.VOCABULARY_HASH


def test_the_hash_moves_when_a_definition_moves():
    rows = ev.table()
    rows[0] = {**rows[0], "definition": rows[0]["definition"] + " (edited)"}
    assert ev.vocabulary_hash(rows) != ev.VOCABULARY_HASH


def test_the_hash_moves_when_the_order_moves():
    """Row order is part of the contract: the JSON Schema enum is generated from
    it, so two corpora typed against different orders are different corpora."""
    rows = ev.table()
    rows[1], rows[2] = rows[2], rows[1]
    assert ev.vocabulary_hash(rows) != ev.VOCABULARY_HASH


def test_magnitude_thresholds_are_contiguous_and_extreme_has_no_ceiling():
    lo_prev = None
    for bucket in ev.MAGNITUDE_BUCKETS:
        lo, hi = ev.MAGNITUDE_THRESHOLDS[bucket]
        if lo_prev is not None:
            assert lo == lo_prev, f"{bucket} does not start where the previous bucket ended"
        lo_prev = hi
    assert ev.MAGNITUDE_THRESHOLDS["EXTREME"][1] is None
    assert ev.MAGNITUDE_THRESHOLDS["LARGE"][0] == 0.05


def test_an_unknown_id_is_a_refusal_that_names_the_vocabulary():
    with pytest.raises(KeyError) as exc:
        ev.by_id("analyst_rating_change")
    assert "frozen L2 vocabulary" in str(exc.value)
    assert ev.VOCABULARY_HASH[:12] in str(exc.value)


def test_scenario_forecasts_reads_the_same_40_ids():
    """X3's grader keys on these ids. Two tuples that must never diverge."""
    assert sf.EVENT_TYPES == ev.EVENT_TYPES
    assert tuple(sf.MAGNITUDES) == ev.MAGNITUDE_BUCKETS


def test_the_declaration_carries_what_a_receipt_needs():
    d = ev.declaration()
    assert d["vocabulary_hash"] == ev.VOCABULARY_HASH
    assert d["n_types"] == 40 and d["n_substantive"] == 39
    assert d["refusal_class"] == "no_event"
    assert set(d["kappa_protocol"]) == {"event_type", "direction",
                                        "magnitude_bucket", "confidence", "sample"}
    assert "no value for 'I do not know'" in d["no_fourth_direction"]
