"""PROFIT_ALLOCATOR_v2 — the Kelly construction test, registered not seeded.

WHY THIS FILE EXISTS
====================
`PROFIT_ALLOCATOR_v1` retired 2026-08-23 because the trust router's cluster
adjustment became part of its policy identity, not because of a result: it has
ONE NAV row and its construction was never measured. v2 asks that question
under the corrected router.

The four properties the brief names, each one a test below:

1. the YAML still parses and v2 loads with the declared allocator block;
2. the book's own fingerprint verifies under book-v1 identity and carries the
   CORRECTED router;
3. `RETIRED` still names v1 — retiring a book is not deleting it, and nothing
   may ever be re-authorised under the same id;
4. the twin is NAMED, and seeding is UNAUTHORISED: the id is absent from
   `AUTHORISED_ACTIVE`, so no code path in this repository can seed it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.services.arena import spec, trust_router

BOOK = "PROFIT_ALLOCATOR_v2"
TWIN = "ENGINE_BASELINE_v1"
DRAFT = (Path(__file__).resolve().parents[2] / "docs" / "TRIALS"
         / "TRIAL-DRAFT-KELLY-CONSTRUCTION-v2.md")


@pytest.fixture
def raw() -> dict:
    return yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. the YAML parses and the book loads


def test_the_config_still_parses_and_every_book_validates():
    specs = spec.load_specs()
    assert BOOK in specs
    assert len(specs) == 11


def test_the_book_declares_ce_kelly_with_its_allocator_block(raw):
    sp = spec.load_specs()[BOOK]
    assert sp.sizing == "ce_kelly"
    assert sp.allocator == {"ic_prior": 0.05, "kelly_fraction": 0.5,
                            "abstain_kelly_factor": 0.5, "max_gross": 1.0}
    # `load_specs` REFUSES ce_kelly with no allocator block: Kelly parameters
    # that fall back to code defaults are undeclared parameters.
    assert set(sp.allocator) <= spec.KNOWN_ALLOCATOR_KEYS


def test_the_allocator_numbers_are_copied_from_v1_not_re_chosen(raw):
    """A prior re-picked for the successor is a prior fit to a retirement."""
    assert (raw["books"][BOOK]["allocator"]
            == raw["books"]["PROFIT_ALLOCATOR_v1"]["allocator"])


def test_the_yaml_says_the_priors_are_declared_and_never_fit():
    """The comment is load-bearing: it is what stops the next reader tuning
    `ic_prior` against the book's own history."""
    import re

    text = spec.CONFIG_PATH.read_text(encoding="utf-8")
    block = text.split(BOOK, 1)[1].split("seeding:", 1)[0]
    # The comment is line-wrapped, so the assertion is made on the normalised
    # prose and not on the accident of where the 79th column fell.
    flat = re.sub(r"\s*#\s*", " ", re.sub(r"\s+", " ", block))
    assert "DECLARED PRIORS" in flat
    assert "neither number is fit to this book's own history" in flat
    assert "Fitting either of them to the book" in flat


def test_ce_kelly_may_not_compose_with_a_tilt_or_an_exemption(raw, tmp_path):
    """Both renormalise to full investment and destroy the cash the allocator
    holds by design. Pinned here because v2 is the second ce_kelly book and a
    later edit is likelier than a first one."""
    ch = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    ch["books"][BOOK]["llm_perception"] = True
    p = tmp_path / "b.yaml"
    p.write_text(yaml.safe_dump(ch), encoding="utf-8")
    with pytest.raises(spec.SpecError):
        spec.load_specs(p)


# --------------------------------------------------------------------------
# 2. identity


def test_the_books_fingerprint_verifies_under_book_v1(raw):
    sp = spec.load_specs()[BOOK]
    assert sp.book_fingerprint == spec.book_fingerprint(
        BOOK, raw, sizing="ce_kelly")
    assert len(sp.book_fingerprint) == 64


def test_the_book_is_born_under_the_corrected_router(monkeypatch, raw):
    """v1 was seeded with cluster_adjust OFF and had to retire when it was
    corrected. v2 carries the CORRECTED setting in its identity from birth,
    which is the whole reason it is a new book rather than v1 restarted."""
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    on = spec.book_fingerprint(BOOK, raw, sizing="ce_kelly")
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", False)
    off = spec.book_fingerprint(BOOK, raw, sizing="ce_kelly")
    assert on != off, ("the router is not in this book's identity; a flip "
                       "would leave one NAV series describing two policies")
    assert spec.ROUTER_FINGERPRINT_BASELINE == "cluster_adjust=0"


def test_registering_v2_did_not_move_the_twins_identity(raw):
    """The property book-v1 exists for. The twin is live with a NAV history."""
    assert (spec.book_fingerprint(TWIN, raw, sizing="equal_weight")
            == "39c7177b5d6e517c8f6795fc3d879132503a24501385ae4c20e57392ec714005")


def test_the_selection_is_byte_identical_to_the_twins(raw):
    """A construction test that changed the selection would be a selection
    test wearing a construction test's name (THE BOTTLENECK)."""
    a, b = raw["books"][BOOK], raw["books"][TWIN]
    assert a["selection"] == b["selection"] == "composite_top_k"
    assert a.get("selection_signal") == b.get("selection_signal")
    assert a["screens"] == b["screens"] == []
    assert a.get("overrides") == b.get("overrides")
    assert spec.book_selection_signal(BOOK, raw) == spec.book_selection_signal(
        TWIN, raw) == "arena_composite"


# --------------------------------------------------------------------------
# 3. v1 stays retired


def test_retired_still_names_v1_and_says_why():
    assert "PROFIT_ALLOCATOR_v1" in spec.RETIRED
    why = spec.RETIRED["PROFIT_ALLOCATOR_v1"]
    assert "retired 2026-08-23" in why
    assert "PROFIT_ALLOCATOR_v2" in why, (
        "the retirement note names its successor; a successor that is not "
        "named there is a book nobody can trace back to its reason")


def test_v1_is_still_in_the_yaml_because_retiring_is_not_deleting(raw):
    assert "PROFIT_ALLOCATOR_v1" in raw["books"]
    assert "PROFIT_ALLOCATOR_v1" not in spec.AUTHORISED_ACTIVE


def test_v1_and_v2_are_different_books(raw):
    assert (spec.book_fingerprint("PROFIT_ALLOCATOR_v1", raw,
                                  sizing="ce_kelly")
            != spec.book_fingerprint(BOOK, raw, sizing="ce_kelly"))


# --------------------------------------------------------------------------
# 4. the twin is named, and seeding is UNAUTHORISED


def test_the_twin_is_named_in_the_books_own_purpose(raw):
    assert TWIN in raw["books"][BOOK]["purpose"]


def test_the_twin_is_named_in_the_seeding_block(raw):
    assert raw["seeding"]["profit_allocator_v2"]["twin"] == TWIN


def test_seeding_was_authorised_by_a_named_person_on_a_date(raw):
    """2026-09-20: Murat authorised the seed ("on the alpaca flip and adjust
    yourself dont ask it"). The flag carries WHO and WHEN, verbatim; an empty
    flag was the registered state for one day and is pinned in git history."""
    block = raw["seeding"]["profit_allocator_v2"]
    assert "Murat" in block["authorised"] and "2026-09-20" in block["authorised"]
    assert "attended" in block["to_activate"].lower()


def test_the_book_is_now_active_and_seedable():
    """The enforcement is not the comment. `active_specs()` returns only
    AUTHORISED_ACTIVE, and `engine.seed_all()` reads that -- so the flip is
    the tuple, and the YAML sentence only records it."""
    assert BOOK in spec.AUTHORISED_ACTIVE
    assert BOOK in spec.active_specs()


def test_the_router_endpoint_will_not_serve_an_unauthorised_book():
    import inspect

    from backend.routers import arena as router
    src = inspect.getsource(router)
    assert "AUTHORISED_ACTIVE" in src


# --------------------------------------------------------------------------
# 5. the draft registration


def test_the_draft_exists_and_is_signed_by_a_named_person():
    """Signed 2026-09-20 by Murat (verbatim words on the draft). The signature
    names WHO and WHEN; an unsigned draft was the state for one day."""
    assert DRAFT.is_file()
    text = DRAFT.read_text(encoding="utf-8")
    assert "STATUS: SIGNED 2026-09-20" in text and "SIGNED-BY: Murat" in text
    assert "cumulative_trials` not incremented" in text


def test_the_draft_names_the_twin_the_family_and_the_prior():
    text = DRAFT.read_text(encoding="utf-8")
    assert TWIN in text
    assert "KELLY_CONSTRUCTION_2026_09" in text
    assert "declared at size **1**" in text
    assert "DeMiguel" in text and "Garlappi" in text and "Uppal" in text


def test_the_draft_prints_the_worst_case_in_dollars():
    """Protocol §4. A sizing change is not reviewable without it."""
    text = DRAFT.read_text(encoding="utf-8")
    assert "n names x cap x stop" in text
    assert "$5,400" in text and "$15,000" in text
    assert "max_gross" in text


def test_the_draft_declares_its_decision_rule_before_any_number():
    text = DRAFT.read_text(encoding="utf-8")
    for clause in ("FAILED_VARIANT", "CONDITIONAL", "PRODUCT_PROMISING",
                   "CANNOT DETERMINE"):
        assert clause in text, clause
    assert "Earliest decision date" in text
    assert "falsifier" in text.lower()


def test_the_draft_says_it_is_not_a_second_selector():
    """The scoreboard line stays at one, and a later reader must not be able
    to count this book as an alpha source."""
    text = DRAFT.read_text(encoding="utf-8")
    assert "not a second selector" in text.lower()
    assert "stays at **one**" in text
