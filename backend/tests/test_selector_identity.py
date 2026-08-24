"""Book identity must carry what the book CONSUMES — and nothing else.

THE DEFECT THIS PINS
====================
`information_bus` shipped with tests proving `composite_fingerprint()` moves
for the right reasons. Nothing consumed it. `spec.book_fingerprint` still ended
with the bare global `COMPOSITE_VERSION`, so the bus was an audit surface and
the loop it claimed to close was open at both ends:

  * a family admitted to the composite re-identified the books only if somebody
    hand-bumped a string;
  * a future selector that reads NONE of the composite would have been
    re-identified every time the composite changed.

The second is the one that blocks the roadmap. "A new mechanism arrives as its
own book" is only true if the books are independently identified.

THE THREE PROPERTIES, stated as the external review stated them:

  1. adding a real ADMITTED_TO_STATE family changes NO composite book;
  2. promoting it to the composite changes EVERY composite-consuming book;
  3. changing the composite does NOT move an independent selector's book.

Plus the two that make the mechanism trustworthy rather than merely present:
re-weighting without renaming still drifts (the string-bump defect, closed),
and an undeclared selector is REFUSED rather than defaulted to the composite's
dependencies.

AND THE MIGRATION PIN. The nine live books are still on the legacy whole-file
scheme and take their per-book stamp on their next arena pass. Until then, the
value this formula produces must equal the legacy `payload|COMPOSITE_VERSION`
exactly, or all ten NAV histories strand behind `assert_config_current`.
"""

from __future__ import annotations

import hashlib

import pytest
import yaml

from backend.services.arena import discovery, information_bus, spec
from backend.services.arena import selector_identity as si


@pytest.fixture
def raw():
    return yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))


def _fps(cfg: dict) -> dict[str, str]:
    return {b: spec.book_fingerprint(b, cfg,
                                     sizing=(cfg["books"][b] or {}).get("sizing"))
            for b in cfg["books"]}


@pytest.fixture
def bus_sandbox():
    """Restore FAMILIES and COMPOSITE_WEIGHTS however the test exits.

    Both are module-level dicts that live for the process; a test that admitted
    a family and died would leave every later test measuring a different arena.
    """
    fam = {k: dict(v) for k, v in information_bus.FAMILIES.items()}
    wts = dict(discovery.COMPOSITE_WEIGHTS)
    pre = dict(discovery.SCORE_PREFIXES)
    yield
    information_bus.FAMILIES.clear()
    information_bus.FAMILIES.update(fam)
    discovery.COMPOSITE_WEIGHTS.clear()
    discovery.COMPOSITE_WEIGHTS.update(wts)
    discovery.SCORE_PREFIXES.clear()
    discovery.SCORE_PREFIXES.update(pre)


# ---------------------------------------------------------- the migration pin


def test_todays_fingerprints_are_BYTE_IDENTICAL_to_the_legacy_formula(raw):
    """The nine live books have not taken their per-book stamp yet.

    They migrate on the next arena pass, and `assert_config_current` migrates
    only while the legacy whole-file hash still verifies. So this change had to
    be a no-op at today's inputs — not "close", identical. That is what the
    `*_BASELINE` constants buy, and this test is what stops someone deleting
    them as redundant.
    """
    for book_id in raw["books"]:
        legacy = hashlib.sha256(
            "|".join([spec.book_config_payload(book_id, raw),
                      discovery.COMPOSITE_VERSION]).encode()).hexdigest()
        assert spec.book_fingerprint(book_id, raw) == legacy, book_id


def test_the_baselines_record_history_not_the_current_value():
    """A live baseline that has DIVERGED is a real event, not a stale constant.

    If this fails, the correct response is never to update the constant — that
    silently re-baselines the drift it exists to catch. It is to notice that the
    composite changed and that the books must re-identify.
    """
    assert si.COMPOSITE_FAMILIES_BASELINE == information_bus.composite_fingerprint()
    assert si.COMPOSITE_WEIGHTS_BASELINE == si.composite_weight_fingerprint()


# ------------------------------------------------------- the three properties


def test_1_a_STATE_ONLY_family_drifts_NO_composite_book(raw, bus_sandbox):
    """The roadmap constraint, end to end.

    `insider_cmp` proved the bus fingerprint is blind to state-only families.
    This proves the BOOK is — which is the claim that was never wired.
    """
    before = _fps(raw)
    discovery.SCORE_PREFIXES["event_response"] = "event_response:"
    information_bus.FAMILIES["event_response"] = {
        "status": information_bus.ADMITTED_TO_STATE,
        "source": "options_pit_store + event_store",
        "admitted_at": "2026-08-24",
        "why": "accruing PIT history before EVENT_RESPONSE_v1 exists",
    }
    information_bus.assert_registry_matches_code()      # must stay consistent
    assert _fps(raw) == before


def test_2_promoting_it_to_the_composite_drifts_EVERY_composite_book(
        raw, bus_sandbox):
    """And drifting them is CORRECT — their policy really did change."""
    before = _fps(raw)
    discovery.SCORE_PREFIXES["event_response"] = "event_response:"
    information_bus.FAMILIES["event_response"] = {
        "status": information_bus.ADMITTED_TO_COMPOSITE,
        "source": "options_pit_store + event_store",
        "admitted_at": "2026-08-24",
        "why": "promoted — now changes what every composite book decides",
    }
    discovery.COMPOSITE_WEIGHTS["event_response"] = 0.5
    information_bus.assert_registry_matches_code()
    after = _fps(raw)
    assert set(after) == set(before)
    drifted = [b for b in before if before[b] != after[b]]
    assert sorted(drifted) == sorted(before), (
        "every composite-consuming book must re-identify; these did not: "
        f"{sorted(set(before) - set(drifted))}")


def test_3_the_composite_does_NOT_move_an_INDEPENDENT_selector(
        raw, bus_sandbox):
    """The property that lets the arena hold more than one alpha source.

    An `EVENT_RESPONSE_v1` book reads options and event state. Under the old
    global `COMPOSITE_VERSION` it would have re-identified itself every time
    momentum's blend was touched — coupling two experiments that share nothing
    but a directory.
    """
    si.SELECTORS["event_response_v1"] = {
        "algorithm": lambda: ["event_response@1-lgbm_drift1"],
        "dependencies": {
            "families": (lambda: information_bus.family_fingerprint(
                ["event_response"]), None),
        },
        "reads": lambda: ["event_response"],
        "why": "test fixture",
    }
    try:
        cfg = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
        cfg["books"]["EVENT_RESPONSE_v1"] = {
            "purpose": "arena-independent-selector",
            "policy_version": 1,
            "selection": "event_response_top_k",
            "selection_signal": "event_response_v1",
            "sizing": "equal_weight",
            "screens": [],
            "llm_perception": False,
        }
        before = spec.book_fingerprint("EVENT_RESPONSE_v1", cfg)
        neighbour_before = spec.book_fingerprint("ENGINE_BASELINE_v1", cfg)

        # now change the composite in both ways that drift a composite book
        discovery.COMPOSITE_WEIGHTS["mom_12_1"] = 7.0
        discovery.SCORE_PREFIXES["another_family"] = "another:"
        information_bus.FAMILIES["another_family"] = {
            "status": information_bus.ADMITTED_TO_COMPOSITE,
            "source": "test", "admitted_at": "2026-08-24", "why": "test",
        }
        discovery.COMPOSITE_WEIGHTS["another_family"] = 1.0

        assert spec.book_fingerprint("EVENT_RESPONSE_v1", cfg) == before
        # ... while its composite-selecting neighbour DID move
        assert spec.book_fingerprint("ENGINE_BASELINE_v1",
                                     cfg) != neighbour_before
    finally:
        si.SELECTORS.pop("event_response_v1", None)


# ------------------------------------- what makes it a mechanism, not a label


def test_REWEIGHTING_without_renaming_still_drifts_every_composite_book(
        raw, bus_sandbox):
    """The string-bump defect, closed.

    `mom_12_1: 1.0` -> `2.0` is a different policy with an identical family
    set. Before this module the only thing that made those books re-identify
    was whether the editor also remembered `COMPOSITE_VERSION`.
    """
    before = _fps(raw)
    discovery.COMPOSITE_WEIGHTS["mom_12_1"] = 2.0
    after = _fps(raw)
    assert all(before[b] != after[b] for b in before)


def test_an_UNDECLARED_selector_is_refused_not_defaulted():
    """The dangerous default is 'unknown -> use the composite's identity'."""
    with pytest.raises(si.SelectorNotDeclared):
        si.selector_identity_parts("some_selector_nobody_declared")


def test_every_book_in_the_live_config_declares_a_known_selector():
    mapping = si.assert_books_declare_known_selectors()
    assert set(mapping.values()) == {"arena_composite"}


def test_a_book_selecting_on_an_undeclared_signal_cannot_be_fingerprinted(raw):
    """A book cannot reach the arena with an untracked dependency."""
    cfg = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["books"]["MYSTERY_v1"] = {
        "purpose": "x", "policy_version": 1, "selection": "mystery_top_k",
        "selection_signal": "mystery", "sizing": "equal_weight",
        "screens": [], "llm_perception": False,
    }
    with pytest.raises(si.SelectorNotDeclared):
        spec.book_fingerprint("MYSTERY_v1", cfg)


def test_health_surfaces_the_dependency_and_whether_it_is_at_baseline():
    h = si.health()
    assert h["status"] == "ok"
    comp = h["selectors"]["arena_composite"]
    assert comp["dependencies"]["families"] == information_bus.composite_fingerprint()
    assert comp["at_seed_baseline"] == {"families": True, "weights": True}
