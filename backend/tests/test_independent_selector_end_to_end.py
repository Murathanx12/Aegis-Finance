"""A book that selects on its OWN signal — loaded from a real YAML, ranked by
the real engine path.

WHY THIS FILE EXISTS, AND WHAT THE EXISTING TESTS MISSED
========================================================
`selector_identity` (2026-08-24, P0.2) made book identity dependency-aware so
that an independent selector would not inherit the momentum composite's
dependencies. `book_selection_signal()` honoured a per-book `selection_signal:`
key from that day. The docstring said this was "how the first independent
selector arrives".

It could not arrive. Two things blocked it and neither was covered:

  1. `selection_signal` was absent from `spec.CONSUMED_BOOK_KEYS`, so
     `load_specs()` raised `SpecError: key(s) ['selection_signal'] are neither
     consumed nor declared descriptive` on any file that used it.
  2. `BookSpec.selection_signal` read `self.defaults` — the FILE defaults — so
     even with (1) fixed the engine would have ranked the new book by
     `arena_composite` while its fingerprint claimed a different selector.
     Identity and execution disagreeing is worse than the refusal.

The identity test did not catch either, because it built a raw dict and called
`book_fingerprint()` directly. Both defects live in the LOADER, which that
route never runs. So this file's rule is: **construct a real YAML on disk, call
the real `load_specs()`, and push the resulting spec through the real selection
path.** A test that skips the loader cannot certify the loader.

The temporary selector is registered in `selector_identity.SELECTORS` by the
fixture rather than shipped, because declaring a selector whose feature nothing
computes yet is the "config key that changes nothing" failure this repo refuses
elsewhere. What is being certified here is the MECHANISM — a book pointing
somewhere else is loadable, identifiable and executable — not a specific alpha.
"""

from __future__ import annotations

import textwrap

import pytest

from backend.services.arena import policies, spec as S
from backend.services.arena import selector_identity as SI
from backend.services.arena.engine import _select

INDEPENDENT = "test_independent_selector"

#: Ranked OPPOSITELY to the composite on purpose. If the engine were still
#: ranking by `arena_composite`, this test would pass a "some names came back"
#: assertion — so the two orders are inverted and the assertion is on ORDER.
_DAY_STATE = {
    "names": {
        "AAA": {"status": "ok", "close": 100.0,
                "scores": {"arena_composite": 3.0, INDEPENDENT: -3.0}},
        "BBB": {"status": "ok", "close": 100.0,
                "scores": {"arena_composite": 2.0, INDEPENDENT: -2.0}},
        "CCC": {"status": "ok", "close": 100.0,
                "scores": {"arena_composite": 1.0, INDEPENDENT: -1.0}},
        "DDD": {"status": "ok", "close": 100.0,
                "scores": {"arena_composite": 0.0, INDEPENDENT: 0.0}},
    }
}

_YAML = textwrap.dedent("""\
    schema: arena-v1
    namespace: arena-test
    label: SHADOW_BOOK
    validation_status: PRODUCT_EXPERIMENT

    defaults:
      notional_usd: 100000.0
      benchmark: SPY
      transaction_cost_bps: 5
      slippage_bps: 1
      select_top_k: 2
      max_single_name: 0.15
      min_price: 5.0
      min_priced_fraction: 0.80
      selection_signal: arena_composite

    books:
      COMPOSITE_TWIN_v1:
        purpose: control-twin
        policy_version: 1
        selection: composite_top_k
        sizing: equal_weight
        screens: []
        llm_perception: false

      INDEPENDENT_v1:
        purpose: the-first-book-that-is-not-the-composite
        policy_version: 1
        selection: composite_top_k
        selection_signal: {signal}
        sizing: equal_weight
        screens: []
        llm_perception: false
    """)


@pytest.fixture()
def declared_selector(monkeypatch):
    """Declare the test selector for the duration of one test.

    `baseline=None` on every dependency is the documented shape for a selector
    with no seeded history: it has nothing to be byte-identical to.
    """
    monkeypatch.setitem(SI.SELECTORS, INDEPENDENT, {
        "algorithm": lambda: [f"{INDEPENDENT}@1"],
        "dependencies": {},
        "reads": lambda: ["test_family"],
        "why": "test-only: certifies that a non-composite selector loads.",
    })
    return INDEPENDENT


@pytest.fixture()
def yaml_path(tmp_path, declared_selector):
    p = tmp_path / "arena_books_test.yaml"
    p.write_text(_YAML.format(signal=declared_selector), encoding="utf-8")
    return p


# ── the loader ──────────────────────────────────────────────────────────────


def test_load_specs_ACCEPTS_a_per_book_selection_signal(yaml_path):
    """Defect 1. This raised SpecError before 2026-08-24 evening."""
    specs = S.load_specs(yaml_path)
    assert set(specs) == {"COMPOSITE_TWIN_v1", "INDEPENDENT_v1"}


def test_the_loaded_spec_carries_the_BOOKS_signal_not_the_files(yaml_path):
    """Defect 2. `BookSpec.selection_signal` read file defaults, so this
    returned `arena_composite` — the value the fingerprint said it was NOT."""
    specs = S.load_specs(yaml_path)
    assert specs["INDEPENDENT_v1"].selection_signal == INDEPENDENT
    assert specs["COMPOSITE_TWIN_v1"].selection_signal == "arena_composite"


def test_identity_and_execution_resolve_to_THE_SAME_string(yaml_path):
    """The two resolvers agree by construction, not by two functions that
    happen to be written the same way."""
    import yaml as _yaml
    raw = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    for book_id, sp in S.load_specs(yaml_path).items():
        assert sp.selection_signal == S.book_selection_signal(book_id, raw)


# ── the engine ──────────────────────────────────────────────────────────────


def test_the_ENGINE_ranks_the_independent_book_by_ITS_signal(yaml_path):
    """The end-to-end claim: real YAML -> real loader -> real selection path.

    The two score sets are inverted, so ranking by the wrong one is a visibly
    wrong answer rather than a plausible one.
    """
    specs = S.load_specs(yaml_path)

    twin = _select(specs["COMPOSITE_TWIN_v1"], _DAY_STATE)
    indep = _select(specs["INDEPENDENT_v1"], _DAY_STATE)

    assert [c["ticker"] for c in twin.chosen] == ["AAA", "BBB"]
    assert [c["ticker"] for c in indep.chosen] == ["DDD", "CCC"]
    # and the scores on the receipt are the INDEPENDENT ones
    assert [c["score"] for c in indep.chosen] == [0.0, -1.0]


def test_a_name_missing_the_independent_score_is_EXCLUDED_by_name(yaml_path):
    """Missing is missing. A name the new selector cannot score must leave a
    reason naming THAT selector — not be ranked by whatever else it carries."""
    state = {"names": {**_DAY_STATE["names"],
                       "EEE": {"status": "ok", "close": 100.0,
                               "scores": {"arena_composite": 9.9}}}}
    sel = _select(S.load_specs(yaml_path)["INDEPENDENT_v1"], state)
    assert "EEE" not in [c["ticker"] for c in sel.chosen]
    assert any(e["ticker"] == "EEE" and e["reason"] == f"no_{INDEPENDENT}"
               for e in sel.excluded)


def test_policies_select_is_the_only_ranking_path(yaml_path):
    """Guards the shortcut this test could rot into: if `_select` ever stopped
    forwarding the spec's signal, the tests above would still pass on a
    hard-coded default. This asserts the forwarding itself."""
    seen = {}
    real = policies.select

    def spy(day_state, **kw):
        seen.update(kw)
        return real(day_state, **kw)

    specs = S.load_specs(yaml_path)
    try:
        policies.select = spy
        _select(specs["INDEPENDENT_v1"], _DAY_STATE)
    finally:
        policies.select = real
    assert seen["signal"] == INDEPENDENT
    assert seen["top_k"] == 2


# ── identity ────────────────────────────────────────────────────────────────


def test_the_independent_book_does_NOT_carry_the_composites_identity(yaml_path):
    """The point of P0.2: re-weighting the composite must not re-identify a
    book that never reads it."""
    import yaml as _yaml
    raw = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    parts = SI.selector_identity_parts(
        S.book_selection_signal("INDEPENDENT_v1", raw))
    assert parts == [f"{INDEPENDENT}@1"]
    assert not any("universe_quality" in p for p in parts)

    specs = S.load_specs(yaml_path)
    assert (specs["INDEPENDENT_v1"].book_fingerprint
            != specs["COMPOSITE_TWIN_v1"].book_fingerprint)


def test_adding_the_independent_book_does_not_move_the_TWINS_fingerprint(
        tmp_path, declared_selector):
    """Per-book identity means per-book. A new book in the file must leave
    every existing book's fingerprint alone, or seeding one strands the rest."""
    solo = tmp_path / "solo.yaml"
    both = tmp_path / "both.yaml"
    full = _YAML.format(signal=declared_selector)
    solo.write_text(full.split("  INDEPENDENT_v1:")[0], encoding="utf-8")
    both.write_text(full, encoding="utf-8")
    assert (S.load_specs(solo)["COMPOSITE_TWIN_v1"].book_fingerprint
            == S.load_specs(both)["COMPOSITE_TWIN_v1"].book_fingerprint)


# ── the refusal ─────────────────────────────────────────────────────────────


def test_an_UNDECLARED_selector_refuses_at_load_and_names_the_book(tmp_path):
    """A book may not select on a signal whose information dependencies
    nothing tracks — and the error has to say WHICH book, because the file
    holds ten."""
    p = tmp_path / "bad.yaml"
    p.write_text(_YAML.format(signal="a_signal_nobody_declared"),
                 encoding="utf-8")
    with pytest.raises(S.SpecError) as exc:
        S.load_specs(p)
    assert "INDEPENDENT_v1" in str(exc.value)
    assert "a_signal_nobody_declared" in str(exc.value)


def test_the_default_selector_is_ONE_constant(yaml_path):
    """The divergence that was there: identity fell back to `arena_composite`,
    execution fell back to `multifactor_score`. Production declares the key so
    neither fallback ever fired — which is why it survived."""
    assert S.DEFAULT_SELECTION_SIGNAL == "arena_composite"
    bare = S.BookSpec(book_id="X", purpose="", policy_version=1,
                      selection="composite_top_k", sizing="equal_weight",
                      screens=(), llm_perception=False)
    assert bare.selection_signal == S.DEFAULT_SELECTION_SIGNAL
    assert S.book_selection_signal("X", {"books": {"X": {}}}) == \
        S.DEFAULT_SELECTION_SIGNAL
