"""A book's identity must depend on ITS rules, not on its neighbours.

THE DEFECT
==========
`config_hash` hashed the whole YAML, so segment identity was a property of the
FILE. Measured 2026-08-23: a comment-only edit drifted 10 of 10 seeded books,
and every one of them would have refused to run under its own inception.

That made the arena structurally unable to gain a challenger without destroying
every NAV history it had — a direct blocker on the profit-first roadmap, whose
whole premise is generating challengers quickly.

Per-book identity (scheme "book-v1") is strictly MORE precise, never weaker:
this book's own block, the file-level defaults it inherits, and the
common-world facts that make the factorial comparable. The three properties
below are what "more precise, not weaker" means, and all three are asserted.

THE MIGRATION is the risky part, so it is tested harder than the feature: ten
live seeds carry only the legacy fingerprint, and a migration that stamped the
wrong value would silently bless a drifted book forever.
"""

from __future__ import annotations

import json

import pytest
import yaml

from backend.services.arena import spec, store, trust_router


@pytest.fixture
def raw():
    return yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))


def _fps(cfg: dict) -> dict[str, str]:
    return {b: spec.book_fingerprint(b, cfg,
                                     sizing=cfg["books"][b].get("sizing"))
            for b in cfg["books"]}


# ------------------------------------------------- the three properties


def test_an_unrelated_edit_drifts_NOTHING(raw, tmp_path):
    """The defect, pinned. A comment used to drift all ten."""
    p = tmp_path / "b.yaml"
    p.write_text(spec.CONFIG_PATH.read_text(encoding="utf-8")
                 + "\n# a harmless trailing comment\n", encoding="utf-8")
    edited = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert _fps(raw) == _fps(edited)


def test_adding_a_new_book_drifts_NOTHING(raw):
    """Otherwise the arena can never gain a challenger."""
    before = _fps(raw)
    added = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    added["books"]["A_BRAND_NEW_BOOK_v1"] = dict(
        added["books"]["ENGINE_BASELINE_v1"])
    after = _fps(added)
    for b in before:
        assert before[b] == after[b], f"{b} drifted when a sibling was added"


def test_changing_a_books_OWN_rule_drifts_ONLY_it(raw):
    before = _fps(raw)
    ch = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    ch["books"]["CURRENT_BEST_v1"]["sizing"] = "equal_weight"
    after = _fps(ch)
    drifted = [b for b in before if before[b] != after[b]]
    assert drifted == ["CURRENT_BEST_v1"], drifted


def test_changing_the_COMMON_WORLD_drifts_every_book(raw):
    """Costs, benchmark and the information gates are the shared world the
    factorial is judged in. A book quietly running on cheaper fills would make
    every comparison incomparable while its own hash still verified."""
    before = _fps(raw)
    ch = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    ch["defaults"]["transaction_cost_bps"] = 99
    after = _fps(ch)
    assert all(before[b] != after[b] for b in before)


def test_router_setting_still_scopes_to_consuming_books(raw, monkeypatch):
    """Toggle from the SEEDED baseline (off) — the live default is now on."""
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", False)
    before = _fps(raw)
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    after = _fps(raw)
    drifted = [b for b in before if before[b] != after[b]]
    assert drifted == ["PROFIT_ALLOCATOR_v1"], drifted


# ---------------------------------------------------------- the migration


def _legacy_seed(sp, tmp_path) -> dict:
    """A seed as written by the OLD scheme: no book_fingerprint, no scheme."""
    rec = store.seed_book(sp, root=tmp_path)
    p = store.seed_path(sp.book_id, tmp_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("book_fingerprint", None)
    d.pop("fingerprint_scheme", None)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d


def test_a_legacy_seed_migrates_on_first_contact(tmp_path):
    sp = spec.load_specs()["ENGINE_BASELINE_v1"]
    legacy = _legacy_seed(sp, tmp_path)
    assert "book_fingerprint" not in legacy

    rec = store.assert_config_current(sp, root=tmp_path)
    assert rec["fingerprint_scheme"] == "book-v1"
    assert rec["book_fingerprint"] == sp.book_fingerprint
    assert rec["fingerprint_migrated_at"]


def test_migration_preserves_the_inception(tmp_path):
    """Adding a sharper claim must not restate the original one."""
    sp = spec.load_specs()["ENGINE_BASELINE_v1"]
    legacy = _legacy_seed(sp, tmp_path)
    rec = store.assert_config_current(sp, root=tmp_path)
    for k in ("book_id", "seeded_at", "config_hash", "policy_fingerprint",
              "notional_usd", "benchmark"):
        assert rec[k] == legacy[k], f"{k} was altered by the migration"


def test_migration_REFUSES_when_the_config_already_changed(tmp_path,
                                                           monkeypatch):
    """THE dangerous case.

    Stamping per-book identity from a config that has already drifted would
    bless the drift permanently. The migration must refuse and say so.
    """
    sp = spec.load_specs()["ENGINE_BASELINE_v1"]
    _legacy_seed(sp, tmp_path)
    drifted = spec.BookSpec(**{**sp.__dict__, "config_hash": "0" * 64})
    with pytest.raises(store.ConfigDrift) as e:
        store.assert_config_current(drifted, root=tmp_path)
    assert "refusing to migrate" in str(e.value)


def test_migration_is_idempotent(tmp_path):
    sp = spec.load_specs()["ENGINE_BASELINE_v1"]
    _legacy_seed(sp, tmp_path)
    first = store.assert_config_current(sp, root=tmp_path)
    second = store.assert_config_current(sp, root=tmp_path)
    assert first["fingerprint_migrated_at"] == second["fingerprint_migrated_at"]


def test_after_migration_a_changed_rule_is_REFUSED(tmp_path, monkeypatch):
    """The whole point of identity: it must still catch real drift."""
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", False)
    sp = spec.load_specs()["PROFIT_ALLOCATOR_v1"]
    _legacy_seed(sp, tmp_path)
    store.assert_config_current(sp, root=tmp_path)          # migrates

    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    flipped = spec.load_specs()["PROFIT_ALLOCATOR_v1"]
    with pytest.raises(store.ConfigDrift):
        store.assert_config_current(flipped, root=tmp_path)


def test_a_migrated_book_is_immune_to_a_sibling_being_added(tmp_path):
    """The payoff: after migration, adding a challenger cannot halt a book."""
    sp = spec.load_specs()["ENGINE_BASELINE_v1"]
    _legacy_seed(sp, tmp_path)
    store.assert_config_current(sp, root=tmp_path)          # migrates

    bigger = yaml.safe_load(spec.CONFIG_PATH.read_text(encoding="utf-8"))
    bigger["books"]["A_NEW_CHALLENGER_v1"] = dict(
        bigger["books"]["ENGINE_BASELINE_v1"])
    p = tmp_path / "bigger.yaml"
    p.write_text(yaml.safe_dump(bigger), encoding="utf-8")

    # config_hash is now different — the legacy scheme would have refused.
    sp2 = spec.load_specs(p)["ENGINE_BASELINE_v1"]
    assert sp2.config_hash != sp.config_hash
    store.assert_config_current(sp2, root=tmp_path)         # must NOT raise


def test_new_seeds_are_written_under_book_v1(tmp_path):
    sp = spec.load_specs()["RISK_SIZED_v1"]
    rec = store.seed_book(sp, root=tmp_path)
    assert rec["fingerprint_scheme"] == "book-v1"
    assert rec["book_fingerprint"] == sp.book_fingerprint


def test_reseeding_a_changed_book_is_still_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", False)
    sp = spec.load_specs()["PROFIT_ALLOCATOR_v1"]
    store.seed_book(sp, root=tmp_path)
    monkeypatch.setattr(trust_router, "CLUSTER_ADJUST_DEFAULT", True)
    with pytest.raises(store.SeedRefused):
        store.seed_book(spec.load_specs()["PROFIT_ALLOCATOR_v1"],
                        root=tmp_path)


# ── legacy identity must not depend on the platform that wrote the file ──
#
# `config_hash` is seed identity for every book still on the legacy scheme, and
# it hashes BYTES. Measured 2026-08-24: this repo's arena config hashes to
# 641adafc on Linux (LF) and 5ae0eccc on a Windows checkout (CRLF, via
# `core.autocrlf=true`). The ten books seeded 2026-08-21 sealed the LF value,
# so a CRLF checkout disagreed with production about what the config IS.
#
# Nothing broke only because git's own text normalisation happened to keep the
# committed blob LF. Turn `core.autocrlf` off on a Windows machine, commit, and
# production's hash moves behind a diff that shows NOTHING — every legacy seed
# refuses to run and, worse, refuses to migrate.
#
# The seeded value is asserted literally because that is the number the live
# books are sealed under. If a deliberate config change moves it, this test is
# supposed to fail and force the attended migration decision.

SEEDED_CONFIG_HASH = (
    "641adafc38703b5c3c898103639cd9e7c1f3608275757b2c93ac74f5f71ef7db")


def test_config_hash_is_invariant_to_line_endings(tmp_path):
    lf = spec.CONFIG_PATH.read_bytes().replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    assert lf != crlf, "fixture is not exercising the difference"

    a, b = tmp_path / "lf.yaml", tmp_path / "crlf.yaml"
    a.write_bytes(lf)
    b.write_bytes(crlf)
    assert spec.config_hash(a) == spec.config_hash(b)


def test_the_live_books_still_hash_to_what_they_were_seeded_under():
    assert spec.config_hash() == SEEDED_CONFIG_HASH


def test_a_crlf_checkout_agrees_with_production(tmp_path):
    crlf = tmp_path / "crlf.yaml"
    crlf.write_bytes(
        spec.CONFIG_PATH.read_bytes().replace(b"\r\n", b"\n")
                                     .replace(b"\n", b"\r\n"))
    assert spec.config_hash(crlf) == SEEDED_CONFIG_HASH


# --------------------------------------------------------------------------
# The status endpoint has to SERVE identity, because a gate that reads a key
# the payload never contains reports a failure no state of the system can
# clear. `monday_gate_check` printed "seed migration -> book-v1  0/9 stamped
# [FAIL]" for weeks against seeds whose real state was simply invisible.
# --------------------------------------------------------------------------
def test_status_serves_book_identity_fields(tmp_path, monkeypatch):
    from backend.services.arena import engine

    st = engine.status()
    assert "books" in st
    for book_id, v in st["books"].items():
        assert "fingerprint_scheme" in v, (
            f"{book_id}: status must SERVE fingerprint_scheme even when it is "
            f"None — monday_gate_check reads it, and a missing key reads as "
            f"'not migrated' rather than 'not served'")
        assert "book_fingerprint" in v
        assert "composite_version" in v


def test_status_book_fingerprint_is_truncated_not_whole():
    """A status endpoint is a public surface; the fingerprint identifies a
    book there, it does not have to be the whole digest."""
    from backend.services.arena import engine

    for v in engine.status()["books"].values():
        bfp = v.get("book_fingerprint")
        if bfp is not None:
            assert len(bfp) <= 12
