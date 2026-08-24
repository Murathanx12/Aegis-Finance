"""P0.2 — admitting information must be a policy event, not a diff.

The roadmap states the hard constraint:

    the seeded books' `policy_fingerprint` must not change when a field they do
    not consume is added.

That is the property these tests exist to pin, and it is not free: every book's
fingerprint carries `COMPOSITE_VERSION`, so before this module any change to the
estimator drifted all ten books at once — including books that would never read
the new family.
"""

from __future__ import annotations

import pytest
import yaml

from backend.services.arena import information_bus as bus
from backend.services.arena import spec


@pytest.fixture
def raw():
    return yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))


def _fps(cfg):
    return {b: spec.book_fingerprint(b, cfg,
                                     sizing=cfg["books"][b].get("sizing"))
            for b in cfg["books"]}


# ── the constraint the roadmap names ────────────────────────────────────────


def test_admitting_a_STATE_ONLY_family_drifts_NO_BOOK(raw, monkeypatch):
    """The whole point. A family no book consumes must cost nothing.

    This is what lets a new mechanism accumulate PIT history BEFORE its book
    exists — which matters because history cannot be backfilled for anything a
    vendor does not keep.
    """
    before_books = _fps(raw)
    before_composite = bus.composite_fingerprint()

    fam = dict(bus.FAMILIES)
    fam["some_new_signal"] = {
        "status": bus.ADMITTED_TO_STATE,
        "source": "a future collector",
        "admitted_at": "2026-08-24",
        "why": "accruing history ahead of the selector that will read it",
    }
    monkeypatch.setattr(bus, "FAMILIES", fam)

    assert bus.composite_fingerprint() == before_composite
    assert _fps(raw) == before_books
    assert bus.bus_version() != "", "the bus itself still records the event"


def test_the_BUS_VERSION_does_move_so_the_event_is_recorded(monkeypatch):
    """Nothing drifts, but the admission is not invisible either."""
    before = bus.bus_version()
    fam = dict(bus.FAMILIES)
    fam["some_new_signal"] = {
        "status": bus.ADMITTED_TO_STATE, "source": "x",
        "admitted_at": "2026-08-24", "why": "y",
    }
    monkeypatch.setattr(bus, "FAMILIES", fam)
    assert bus.bus_version() != before


def test_admitting_a_COMPOSITE_family_DOES_move_the_composite_fingerprint(
        monkeypatch):
    """The other half. A family that changes what books DECIDE must drift
    them: a NAV series spanning the change would describe two policies."""
    before = bus.composite_fingerprint()
    fam = dict(bus.FAMILIES)
    fam["some_new_signal"] = {
        "status": bus.ADMITTED_TO_COMPOSITE, "source": "x",
        "admitted_at": "2026-08-24", "why": "y",
    }
    monkeypatch.setattr(bus, "FAMILIES", fam)
    assert bus.composite_fingerprint() != before


def test_editing_a_families_REASON_drifts_NOTHING(monkeypatch):
    """Documentation is not policy.

    The first version of `composite_fingerprint` hashed the whole entry, so
    rewording a `why` re-identified every composite book — reintroducing the
    exact comment-only-edit defect that drifted 10 of 10 books on 2026-08-23.
    Prose moves `bus_version` (the audit record) and nothing else.
    """
    before_fp = bus.composite_fingerprint()
    before_ver = bus.bus_version()
    fam = {k: dict(v) for k, v in bus.FAMILIES.items()}
    fam["mom_12_1"]["why"] = "reworded entirely, meaning unchanged"
    monkeypatch.setattr(bus, "FAMILIES", fam)
    assert bus.composite_fingerprint() == before_fp
    assert bus.bus_version() != before_ver, "the edit is still on the record"


def test_moving_a_family_between_STATUSES_does_drift_the_composite(monkeypatch):
    """Names-only hashing must not go so far that a real policy change hides.
    Promoting a state-only family into the composite changes what books decide.
    """
    before = bus.composite_fingerprint()
    fam = {k: dict(v) for k, v in bus.FAMILIES.items()}
    fam["insider_cmp"]["status"] = bus.ADMITTED_TO_COMPOSITE
    monkeypatch.setattr(bus, "FAMILIES", fam)
    assert bus.composite_fingerprint() != before


# ── the registry cannot silently disagree with the code ─────────────────────


def test_the_declared_bus_matches_what_the_state_actually_reads():
    rep = bus.assert_registry_matches_code()
    assert rep["n_composite"] == 6
    assert "insider_cmp" in rep["state_families"]


def test_a_family_in_CODE_but_not_DECLARED_is_REFUSED(monkeypatch):
    """The undeclared-widening direction: every book's inputs grew and nothing
    said so."""
    from backend.services.arena import discovery
    monkeypatch.setattr(discovery, "SCORE_PREFIXES",
                        {**discovery.SCORE_PREFIXES, "sneaky": "sneaky:"})
    with pytest.raises(bus.BusDrift) as e:
        bus.assert_registry_matches_code()
    assert "Undeclared" in str(e.value) and "sneaky" in str(e.value)


def test_a_family_DECLARED_but_absent_from_code_is_REFUSED(monkeypatch):
    """The other direction: a book believing it decides on something it never
    sees."""
    fam = dict(bus.FAMILIES)
    fam["ghost"] = {"status": bus.ADMITTED_TO_STATE, "source": "nowhere",
                    "admitted_at": "2026-08-24", "why": "does not exist"}
    monkeypatch.setattr(bus, "FAMILIES", fam)
    with pytest.raises(bus.BusDrift) as e:
        bus.assert_registry_matches_code()
    assert "declared but absent" in str(e.value)


def test_a_composite_weight_declared_only_as_STATE_is_REFUSED(monkeypatch):
    """A family that changes decisions cannot hide as state-only — that would
    let an estimator change without drifting the books it changed."""
    fam = {k: dict(v) for k, v in bus.FAMILIES.items()}
    fam["pead"]["status"] = bus.ADMITTED_TO_STATE
    monkeypatch.setattr(bus, "FAMILIES", fam)
    with pytest.raises(bus.BusDrift) as e:
        bus.assert_registry_matches_code()
    assert "ADMITTED_TO_COMPOSITE" in str(e.value)


def test_a_family_without_a_REASON_is_REFUSED(monkeypatch):
    fam = {k: dict(v) for k, v in bus.FAMILIES.items()}
    fam["pead"]["why"] = ""
    monkeypatch.setattr(bus, "FAMILIES", fam)
    with pytest.raises(bus.BusDrift) as e:
        bus.assert_registry_matches_code()
    assert "without a reason" in str(e.value)


def test_an_invalid_status_is_REFUSED(monkeypatch):
    fam = {k: dict(v) for k, v in bus.FAMILIES.items()}
    fam["pead"]["status"] = "PROBABLY_FINE"
    monkeypatch.setattr(bus, "FAMILIES", fam)
    with pytest.raises(bus.BusDrift):
        bus.assert_registry_matches_code()


def test_health_reports_ok_against_the_live_code():
    h = bus.health()
    assert h["status"] == "ok", h
    assert h["n_state_only"] >= 1
