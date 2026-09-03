"""EDGAR 8-K item collector + scenario-bridge event_type wiring.

All offline: the parser and mapping table are pure functions over fixture
dicts, and the tape-status/field-map tests run against tmp_path manifests.
Nothing here opens a socket -- the fast suite's network guard would catch it
if it did, and the live fetch paths (`_Client`, `pull`) are exercised only by
the attended CLI.

The three disciplines under test:
1. ITEM PARSING -- '2.02,9.01' and 'Item 2.02' both normalise; pre-2004 bare
   numbers come back EMPTY, never guessed.
2. PIT -- availability is the EDGAR acceptance timestamp. The event's own date
   is stored but NEVER gates knowability, and the date-range filter runs on
   the FILING date (the knowability clock), not the event date.
3. THE MAPPING TABLE -- every item code is well-formed, every target is a real
   scenario event_type, and `event_type` upgrades UNMAPPABLE -> PROXY only
   when a tape manifest actually exists on disk (derived, never assumed).
"""

from __future__ import annotations

import json

import pytest

from scripts import edgar_8k_items as E8K
from scripts import scenario_bridge as SB


# ------------------------------------------------------------ fixtures

def submissions_fixture() -> dict:
    """A miniature filings.recent block in the API's true column-parallel shape."""
    return {
        "cik": "1045810",
        "filings": {
            "recent": {
                "form": ["8-K", "10-K", "8-K/A", "8-K", "4", "8-K"],
                "filingDate": ["2024-05-22", "2024-02-21", "2024-03-04",
                               "2013-02-13", "2024-06-01", "2026-01-05"],
                "acceptanceDateTime": [
                    "2024-05-22T20:36:12.000Z", "2024-02-21T21:37:12.000Z",
                    "2024-03-04T22:01:00.000Z", "2013-02-13T21:05:00.000Z",
                    "2024-06-01T12:00:00.000Z", "2026-01-05T13:00:00.000Z"],
                # 8-K reportDate = date of EARLIEST EVENT -- before filingDate
                "reportDate": ["2024-05-19", "2024-01-28", "2024-02-28",
                               "2013-02-10", "", "2025-12-30"],
                "accessionNumber": ["a-1", "a-2", "a-3", "a-4", "a-5", "a-6"],
                "items": ["2.02,9.01", "", "Item 5.02, Item 9.01",
                          "2.06", "", "1.02"],
                "primaryDocument": ["d1.htm", "d2.htm", "d3.htm", "d4.htm",
                                    "d5.htm", "d6.htm"],
            },
            "files": [],
        },
    }


# ------------------------------------------------------------ item parsing

def test_normalize_items_handles_both_spellings_and_sorts():
    assert E8K.normalize_items("2.02,9.01") == ["2.02", "9.01"]
    assert E8K.normalize_items("Item 9.01, Item 2.02") == ["2.02", "9.01"]
    assert E8K.normalize_items("5.02") == ["5.02"]


def test_normalize_items_refuses_to_guess_the_old_regime():
    # pre-2004 8-Ks used bare numbers; '5' is NOT '5.02' and must not become it
    assert E8K.normalize_items("5, 7") == []
    assert E8K.normalize_items("") == []
    assert E8K.normalize_items(None) == []


def test_parser_keeps_only_8k_forms_and_parses_items():
    rows = E8K.parse_submissions(submissions_fixture(), cik=1045810,
                                 ticker="NVDA", start="2013-01-01",
                                 end="2026-12-31")
    assert {r["form"] for r in rows} == {"8-K", "8-K/A"}
    assert {r["accession"] for r in rows} == {"a-1", "a-3", "a-4", "a-6"}
    by_acc = {r["accession"]: r for r in rows}
    assert by_acc["a-1"]["items"] == ["2.02", "9.01"]
    assert by_acc["a-3"]["items"] == ["5.02", "9.01"]   # 'Item X' spelling
    assert all(r["cik"] == 1045810 and r["ticker"] == "NVDA" for r in rows)


# ------------------------------------------------------------ PIT

def test_availability_is_the_acceptance_timestamp_never_the_event_date():
    rows = E8K.parse_submissions(submissions_fixture(), cik=1, ticker="X",
                                 start="2013-01-01", end="2026-12-31")
    r = next(x for x in rows if x["accession"] == "a-1")
    # both clocks stored, and they DIFFER: the event happened before the filing
    assert r["event_date"] == "2024-05-19"
    assert r["filing_date"] == "2024-05-22"
    assert r["acceptance_datetime"] == "2024-05-22T20:36:12.000Z"
    assert r["acceptance_datetime"][:10] >= r["filing_date"] > r["event_date"], (
        "if these ever collapse into one date the PIT rule has been erased")


def test_date_range_filters_on_the_knowability_clock_not_the_event_clock():
    # a-6: event 2025-12-30 (inside a 2025 range), FILED 2026-01-05 (outside).
    # It was not knowable inside 2025 and must be excluded.
    rows = E8K.parse_submissions(submissions_fixture(), cik=1, ticker="X",
                                 start="2025-01-01", end="2025-12-31")
    assert rows == []
    # widen the end past the FILING date and it appears
    rows = E8K.parse_submissions(submissions_fixture(), cik=1, ticker="X",
                                 start="2025-01-01", end="2026-01-31")
    assert [r["accession"] for r in rows] == ["a-6"]
    assert rows[0]["event_date"] == "2025-12-30"


def test_coverage_start_is_the_earliest_filing_of_any_form():
    assert E8K.coverage_start_of(submissions_fixture()) == "2013-02-13"


# ------------------------------------------------------------ the mapping table

def test_every_item_code_is_well_formed_and_every_target_is_a_real_event_type():
    legal = set(SB.ENUMS["event_type"])
    for item, targets in SB.EIGHTK_ITEM_EVENT_TYPE.items():
        assert E8K.normalize_items(item) == [item], f"malformed item code {item!r}"
        for t in targets:
            assert t in legal, f"{item} maps to {t!r}, not a scenario event_type"


def test_the_mapping_stays_a_proxy_administrative_items_map_to_nothing():
    # exhibit lists, Reg FD and earnings prints must never fabricate an event
    for admin in ("9.01", "7.01", "2.02", "5.07"):
        assert SB.EIGHTK_ITEM_EVENT_TYPE[admin] == ()
    # and the defensible specifics point where they should
    assert "installed_base_obsolescence" in SB.EIGHTK_ITEM_EVENT_TYPE["2.06"]
    assert "consolidation" in SB.EIGHTK_ITEM_EVENT_TYPE["2.01"]
    assert SB.eightk_items_for("consolidation") == ("2.01", "5.01")


def test_field_map_upgrades_event_type_only_when_the_tape_exists(tmp_path, monkeypatch):
    # no manifest on disk -> UNMAPPABLE, exactly as the static map says
    monkeypatch.setattr(SB, "EIGHTK_MANIFEST", tmp_path / "absent.json")
    fm = SB.field_map_current()
    assert fm["event_type"]["grade"] == "UNMAPPABLE"
    assert SB.mappability_summary(fm) == SB.mappability_summary()

    # manifest present -> PROXY, never DIRECT, and the headline moves
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"rows": 10, "ciks": 2,
                               "filing_date_min": "2013-01-04",
                               "filing_date_max": "2026-09-03"}),
                   encoding="utf-8")
    monkeypatch.setattr(SB, "EIGHTK_MANIFEST", man)
    fm2 = SB.field_map_current()
    assert fm2["event_type"]["grade"] == "PROXY"
    before, after = SB.mappability_summary(), SB.mappability_summary(fm2)
    assert after["unmappable"] == before["unmappable"] - 1
    assert after["direct"] == before["direct"], (
        "an item code is a disclosure category standing in for a mechanism; "
        "upgrading it to DIRECT would claim the panel holds the quantity itself")


def test_retrieval_predicates_are_untouched_by_the_tape(tmp_path, monkeypatch):
    """The tape changes OWNERSHIP, not retrieval: scenario_predicates must
    still report event_type as unmappable-as-a-filter, so every grade in the
    20260903 receipt reproduces bit-for-bit."""
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({"rows": 1, "ciks": 1}), encoding="utf-8")
    monkeypatch.setattr(SB, "EIGHTK_MANIFEST", man)
    scenario = {
        "scenario_id": "T-1", "event_type": "consolidation",
        "analyst_change": "targets_cut", "attention_state": "neglected",
        "holder_action": "unknown",
        "price_state": {"drawdown_state": "deep_drawdown",
                        "momentum_12_1_sign": "negative"},
    }
    _, rep = SB.scenario_predicates(scenario)
    assert "event_type" in rep["unmappable_fields"]
    assert "event_type" not in rep["predicates_used"]


def test_pull_paths_never_leak_into_the_fast_suite():
    """The live client is import-safe (no socket at import), and the module's
    constants carry the SEC courtesies: a contact UA and a sub-10/s throttle."""
    assert "mrthnabdullaev@gmail.com" in E8K.USER_AGENT
    assert 1.0 / E8K.MIN_INTERVAL_S <= 10.0, "SEC guidance is <=10 req/s"
    assert E8K.EIGHTK_FORMS == ("8-K", "8-K/A")
