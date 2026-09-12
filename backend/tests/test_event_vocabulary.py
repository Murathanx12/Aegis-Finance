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


def test_every_v1_row_is_the_specs_row():
    """Section 1.2 is v1 and v1 is FROZEN: the hash rows carry depends on it."""
    spec_rows = _spec_rows()
    assert len(spec_rows) == len(ev.VOCABULARY_V1)
    for (sid, definition, sec_items, prior, magnitude, example, counter), got in zip(
            spec_rows, ev.VOCABULARY_V1):
        assert got.id == sid
        assert got.definition == definition
        assert got.sec_items_text == sec_items
        assert got.direction_prior_text == prior
        assert got.magnitude_bucket == magnitude
        assert got.example == example
        assert got.counter_example == counter


def test_the_v1_count_is_derived_from_the_table_and_the_specs_prose_is_off_by_one():
    """39 substantive + `no_event` = 40. The section heading says "39 event
    types + no_event" (right); its closing sentence says "38 substantive +
    no_event = 39" (wrong). Recorded rather than silently resolved, and the
    module's counters are computed from the table so neither sentence can
    decide the number."""
    assert len(ev.VOCABULARY_V1) == 40
    assert len([t for t in ev.VOCABULARY_V1 if t.id != "no_event"]) == 39
    assert ev.VOCABULARY_V1[-1].id == ev.NO_EVENT == "no_event"
    text = SPEC.read_text(encoding="utf-8")
    assert "That is 38 substantive" in text, (
        "the spec's miscount was fixed -- update this test's record of it")


def test_v2_is_v1_plus_three_analyst_rows_and_no_event_is_still_last():
    """The addendum goes BEFORE the refusal class, so every v1 id keeps its
    position -- row order is part of the contract (the JSON Schema enum is
    generated from it)."""
    assert ev.VOCABULARY_VERSION == 2
    assert ev.N_TYPES == len(ev.VOCABULARY) == 43
    assert ev.N_SUBSTANTIVE == 42
    assert ev.EVENT_TYPES[-1] == ev.NO_EVENT == "no_event"
    assert len(set(ev.EVENT_TYPES)) == ev.N_TYPES, "a duplicate id in the vocabulary"
    added = tuple(t.id for t in ev._V2_ADDED)
    assert added == ("analyst_rating_change", "analyst_target_change",
                     "analyst_initiation")
    assert ev.EVENT_TYPES[-4:-1] == added
    # every v1 id is where it was
    assert ev.EVENT_TYPES[:39] == tuple(t.id for t in ev.VOCABULARY_V1[:39])


def test_the_v1_hash_did_not_move_when_v2_landed():
    """THE PIN. Rows typed before 2026-09-13 carry this hash; if it moves, a
    corpus becomes unreadable against the vocabulary it was typed under. The
    literal is the value `git show` gives for the module at commit 0ef42a8."""
    assert ev.VOCABULARY_HASH_V1 == (
        "b55fcff7ef3e206ffb14b088a832367b1471a59bddbb8d514c4a01fbfc1d2e6a")
    assert ev.vocabulary_hash(ev.table(1)) == ev.VOCABULARY_HASH_V1
    assert ev.VOCABULARY_HASH != ev.VOCABULARY_HASH_V1, (
        "the CURRENT hash must move when the table grows -- that is the signal")
    assert ev.VOCABULARY_HASHES == {1: ev.VOCABULARY_HASH_V1, 2: ev.VOCABULARY_HASH}


def test_the_analyst_rows_are_the_specs_1_2b_rows():
    """Parsed from section 1.2b, not transcribed."""
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("#### Analyst actions (v2)"):
                   text.index("That is 42 substantive")]
    rows = []
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([a-z0-9_]+)`\s*\|(.*)\|\s*$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        assert len(cells) == 6, f"{m.group(1)}: {len(cells)} cells, expected 6"
        rows.append((m.group(1), *cells))
    assert len(rows) == 3
    for (sid, definition, sec_items, prior, magnitude, example, counter), got in zip(
            rows, ev._V2_ADDED):
        assert got.id == sid
        assert got.definition == definition
        assert got.sec_items_text == sec_items
        assert got.direction_prior_text == prior
        assert got.magnitude_bucket == magnitude
        assert got.example == example
        assert got.counter_example == counter


def test_every_analyst_prior_is_ambiguous_because_the_sign_is_in_the_word():
    """A family whose members disagreed on their prior could not be mapped as a
    family, which is exactly why PRODUCT and FINANCING do not get one."""
    for t in ev._V2_ADDED:
        assert t.direction_prior is None, t.id
        assert t.sec_items == (), f"{t.id}: broker research is not an 8-K"


def test_an_unknown_version_names_the_versions_that_exist():
    assert ev.vocabulary_for(1) is ev.VOCABULARY_V1
    assert ev.vocabulary_for(2) is ev.VOCABULARY_V2
    with pytest.raises(KeyError) as exc:
        ev.vocabulary_for(3)
    assert "[1, 2]" in str(exc.value)
    assert "never by editing an existing one" in str(exc.value)


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
    """`analyst_rating_change` used to be this test's unknown id. It is a real
    id at v2, which is the whole point of the version, so the unknown one has
    to be something the table genuinely does not have."""
    assert ev.by_id("analyst_rating_change").magnitude_bucket == "MODERATE"
    with pytest.raises(KeyError) as exc:
        ev.by_id("short_interest_squeeze")
    assert "frozen L2 vocabulary" in str(exc.value)
    assert ev.VOCABULARY_HASH[:12] in str(exc.value)
    assert f"v{ev.VOCABULARY_VERSION}" in str(exc.value)


def test_scenario_forecasts_reads_the_same_43_ids():
    """X3's grader keys on these ids. Two tuples that must never diverge."""
    assert sf.EVENT_TYPES == ev.EVENT_TYPES
    assert tuple(sf.MAGNITUDES) == ev.MAGNITUDE_BUCKETS


def test_the_declaration_carries_what_a_receipt_needs():
    d = ev.declaration()
    assert d["vocabulary_hash"] == ev.VOCABULARY_HASH
    assert d["vocabulary_version"] == 2
    assert d["versions"]["1"]["vocabulary_hash"] == ev.VOCABULARY_HASH_V1
    assert d["versions"]["1"]["n_types"] == 40
    assert d["versions"]["2"]["n_types"] == 43
    assert d["n_types"] == 43 and d["n_substantive"] == 42
    assert d["refusal_class"] == "no_event"
    assert set(d["kappa_protocol"]) == {"event_type", "direction",
                                        "magnitude_bucket", "confidence", "sample"}
    assert "no value for 'I do not know'" in d["no_fourth_direction"]
