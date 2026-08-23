"""Flipping the trust router's cluster adjustment must not rewrite history.

THE HAZARD
==========
`trust_router.CLUSTER_ADJUST_DEFAULT` is measurably the wrong setting: the G1
correlated-worlds battery puts OFF at a 38.7% null-world recommendation rate
against ORDER 27's <=5% bar. So it wants flipping.

But the router's verdict is in a live causal path -- `engine.py` sizes
`ce_kelly` books at `abstain_kelly_factor` of declared aggression unless the
verdict is RECOMMENDED -- and `PROFIT_ALLOCATOR_v1` was seeded 2026-08-21 with
the flag OFF. Flipping it in place would leave ONE live NAV series describing
TWO policies mid-segment, which is precisely the silent-drift the seed
machinery exists to refuse.

THE FIX UNDER TEST
==================
The setting is part of the POLICY IDENTITY of the books that consume it, so a
flip self-refuses: the seeded book raises ConfigDrift and has to be relaunched
as a new immutable version. Two properties have to hold at once, and the second
is the one a careless implementation breaks:

  1. flipping the flag CHANGES the identity of router-consuming books;
  2. NOT flipping it leaves every existing seed verifying byte-for-byte --
     including the router-consuming book's. A guard that breaks the live book
     it protects, at install time, is not a guard.
"""

from __future__ import annotations

import pytest

from backend.services.arena import spec, store, trust_router


@pytest.fixture
def cluster_adjust_on(monkeypatch):
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    yield


@pytest.fixture
def cluster_adjust_off(monkeypatch):
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", False)
    yield


def _fps() -> dict[str, str]:
    return {k: v.policy_fingerprint for k, v in spec.load_specs().items()}


def _router_books() -> list[str]:
    return [k for k, v in spec.load_specs().items()
            if v.sizing in spec.ROUTER_CONSUMING_SIZINGS]


# ------------------------------------------------------- scoping is real


def test_at_least_one_book_consumes_the_router():
    """Otherwise every assertion below is vacuously true."""
    assert _router_books(), "no ce_kelly book — this guard would test nothing"


def test_flipping_cluster_adjust_changes_router_book_identity(
        cluster_adjust_off, monkeypatch):
    before = _fps()
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    after = _fps()
    for book in _router_books():
        assert before[book] != after[book], (
            f"{book} sizes on the router verdict but its policy identity is "
            f"unchanged by the flip — the flip would be silent")


def test_flipping_cluster_adjust_does_NOT_disturb_other_books(
        cluster_adjust_off, monkeypatch):
    before = _fps()
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    after = _fps()
    routers = set(_router_books())
    for book, fp in before.items():
        if book in routers:
            continue
        assert after[book] == fp, (
            f"{book} does not read the router, yet a router change altered "
            f"its identity — that would force nine books to re-seed for a "
            f"fix none of them consume")


# ---------------------------------------- the backward-compatibility half


def test_off_setting_hashes_to_the_legacy_payload(cluster_adjust_off):
    """The seeded books must keep verifying after this guard ships.

    OFF is what the live seeds were written under, so it must contribute
    NOTHING to the payload. If it contributed a segment, installing this guard
    would itself drift PROFIT_ALLOCATOR_v1 and halt it on the next run.
    """
    fps = _fps()
    routers = set(_router_books())
    others = {v for k, v in fps.items() if k not in routers}
    assert len(others) == 1, "non-router books should share one fingerprint"
    assert fps[next(iter(routers))] == others.pop(), (
        "with cluster_adjust OFF the router book must hash identically to "
        "every other book — anything else breaks its existing seed")


def test_baseline_constant_records_the_seeded_setting_not_the_current_one():
    """The baseline is history. Tracking the live default would re-baseline
    the drift it exists to catch."""
    assert spec.ROUTER_FINGERPRINT_BASELINE == "cluster_adjust=0"


def test_router_policy_id_reflects_the_flag(cluster_adjust_on):
    assert spec.router_policy_id() == "cluster_adjust=1"


def test_router_policy_id_off(cluster_adjust_off):
    assert spec.router_policy_id() == "cluster_adjust=0"


# ------------------------------------------------ the refusal, end to end


def test_seeded_book_refuses_to_run_after_the_flip(tmp_path,
                                                   cluster_adjust_off,
                                                   monkeypatch):
    """The whole point: seed under OFF, flip to ON, and the book REFUSES."""
    book = _router_books()[0]
    s_off = spec.load_specs()[book]
    store.seed_book(s_off, root=tmp_path)
    # Same policy, same day: fine.
    store.assert_config_current(s_off, root=tmp_path)

    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    s_on = spec.load_specs()[book]
    with pytest.raises(store.ConfigDrift):
        store.assert_config_current(s_on, root=tmp_path)


def test_reseeding_under_the_flip_is_refused_not_silently_restarted(
        tmp_path, cluster_adjust_off, monkeypatch):
    """A changed policy is a NEW book id, never a new start date for this one."""
    book = _router_books()[0]
    store.seed_book(spec.load_specs()[book], root=tmp_path)
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    with pytest.raises(store.SeedRefused):
        store.seed_book(spec.load_specs()[book], root=tmp_path)
