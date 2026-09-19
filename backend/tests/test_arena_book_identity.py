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
    # BOTH ce_kelly books and only those. v2 (chunk 19) is registered under the
    # CORRECTED router, so it is born carrying `router:cluster_adjust=1` and
    # has no legacy identity to protect -- which is the whole reason it is a
    # new book rather than v1 restarted.
    assert drifted == ["PROFIT_ALLOCATOR_v1", "PROFIT_ALLOCATOR_v2"], drifted


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
#
# IT MOVED ON 2026-09-19, AND THIS IS THAT DECISION, RECORDED.
# ===========================================================
# Chunk 19 registered `PROFIT_ALLOCATOR_v2`. Adding a book changes the WHOLE
# FILE's bytes, so the legacy value moved — and that is precisely the defect
# book-v1 identity was built to stop mattering: `test_adding_a_new_book_drifts_
# NOTHING` above proves the nine live books' OWN fingerprints did not move, and
# those are the values their seeds verify against. The legacy hash is carried
# on receipts and for migrating books still on the old scheme; it is no longer
# the verification key.
#
# The old value is kept beside the new one rather than overwritten, because a
# constant that is silently re-pointed records nothing. And the real invariant
# — the nine live books' per-book fingerprints — is now asserted LITERALLY
# below, where it belongs: pinning the file hash pinned the wrong object, which
# is how this test could go red for a change that broke nothing.

#: The value the ten Gen-1 books were sealed under, 2026-08-21. Historical.
SEEDED_CONFIG_HASH_2026_08_21 = (
    "641adafc38703b5c3c898103639cd9e7c1f3608275757b2c93ac74f5f71ef7db")

#: The whole-file hash as of 2026-09-19 (the registration of PROFIT_ALLOCATOR_v2,
#: chunk 19). Historical.
SEEDED_CONFIG_HASH_2026_09_19 = (
    "e84713bb5e57e847209df28915cccb61d69732c96a6c5fcc4832248cc1a37a6c")

#: The current whole-file hash. Moved 2026-09-20 by ONE edit: the
#: `seeding.profit_allocator_v2.authorised` sentence (Murat's authorisation,
#: verbatim) -- a text change in the seeding block, not in any live book's
#: block, which is exactly the case book-v1 identity was introduced to make
#: harmless (the per-book pins below did not move). This legacy whole-file pin
#: is kept so that a change to the FILE is always a visible test change.
SEEDED_CONFIG_HASH = (
    "fbad6155b88316f438a0dba25f2907a8517b6f473ee9bc5aaabe6cb5f29eec3b")

#: THE INVARIANT THAT ACTUALLY PROTECTS THE LIVE SEEDS. Recorded from the
#: checkout immediately BEFORE the v2 registration and re-verified immediately
#: after: every one is byte-identical across that edit.
LIVE_BOOK_FINGERPRINTS = {
    "ENGINE_BASELINE_v1":
        "39c7177b5d6e517c8f6795fc3d879132503a24501385ae4c20e57392ec714005",
    "RISK_SIZED_v1":
        "df833a0b014eb7656a1044e67448e805979a0d962405ee91990f40e2f9c0e448",
    "WINNER_EXEMPT_v1":
        "4e02b36ee22cd286d798bec031d1d8f24289f7dd75539030b3940da7e01ebe89",
    "ANTI_SIGNAL_v1":
        "9e6d1afcc05f0992397304bd705f9368763a429deb50c7b084723b6a32980e2b",
    "LLM_PERCEPTION_v1":
        "23e811940e8919eddb7c1e6adb27154d8213e992f4b8eec0c24c7cd394bff11b",
    "LLM_EVENTS_v1":
        "ee0ffcfed025f6af2032fa878463686782b93e393fb4dec601c217778c5269d2",
    "CURRENT_BEST_v1":
        "49ce8063bd68b698c09a5edffe7104d88cb5e49ae3ba35bd9bc9d4593c65869c",
    "AGGRESSIVE_TOP5_v1":
        "62af76ad90133769a7887c085d25a449c6138cb390427b34d2d0afab0aab4dc9",
    "DIVERSIFIED_TOP20_v1":
        "698385a3a69c7037739a2ac3c4b31fe7dbdc75dab52d0075fa63286bf97573fd",
    # Under the CORRECTED router, which is why this book is retired.
    "PROFIT_ALLOCATOR_v1":
        "4b9366bbcc6dcc594e0088a21bf1c5989201b4a9c17c5d5a4392da61f77ab1b6",
}


def test_the_live_books_own_fingerprints_did_not_move(raw):
    """The invariant the file hash was standing in for, pinned literally.

    Read under the LIVE router setting -- what the books actually run as today,
    not what they were sealed as in August. `PROFIT_ALLOCATOR_v1` carries the
    corrected router in its identity, which is exactly why it is RETIRED rather
    than running.
    """
    got = _fps(raw)
    for book, want in LIVE_BOOK_FINGERPRINTS.items():
        assert got[book] == want, (
            f"{book}'s OWN identity moved. This is the value its seed verifies "
            f"against; a book whose fingerprint moves must be launched as a new "
            f"immutable version, not edited in place.")


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


# --------------------------------------------------------------------------
# 2026-09-20: the SEED path honours book-v1 identity too. On the deployed
# backend `seed_all` refused ENGINE_BASELINE_v1 -- seeded 08-21, migrated to
# book-v1 -- because the whole-file hash had moved (the seeding sentence for
# PROFIT_ALLOCATOR_v2), and never reached the tenth book. A book-v1 seed is
# identified by its own fingerprint; a legacy seed still by the file.
# --------------------------------------------------------------------------
def test_a_book_v1_seed_survives_a_whole_file_hash_move(tmp_path):
    from backend.services.arena import store
    s = next(iter(spec.active_specs().values()))
    rec = store.seed_book(s, root=tmp_path)
    assert rec["fingerprint_scheme"] == "book-v1"
    p = store.seed_path(s.book_id, tmp_path)
    moved = json.loads(p.read_text(encoding="utf-8"))
    moved["config_hash"] = "0" * 64          # the FILE changed elsewhere
    p.write_text(json.dumps(moved), encoding="utf-8")
    again = store.seed_book(s, root=tmp_path)
    assert again["seeded_at"] == rec["seeded_at"], "the inception did not move"


def test_a_legacy_seed_still_refuses_a_whole_file_hash_move(tmp_path):
    from backend.services.arena import store
    s = next(iter(spec.active_specs().values()))
    rec = store.seed_book(s, root=tmp_path)
    p = store.seed_path(s.book_id, tmp_path)
    legacy = json.loads(p.read_text(encoding="utf-8"))
    legacy.pop("fingerprint_scheme", None)
    legacy.pop("book_fingerprint", None)
    legacy["config_hash"] = "0" * 64
    p.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(store.SeedRefused, match="changed configuration"):
        store.seed_book(s, root=tmp_path)


def test_a_book_v1_seed_still_refuses_its_own_fingerprint_moving(tmp_path):
    from backend.services.arena import store
    s = next(iter(spec.active_specs().values()))
    store.seed_book(s, root=tmp_path)
    p = store.seed_path(s.book_id, tmp_path)
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["book_fingerprint"] = "f" * 64
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(store.SeedRefused, match="changed rule"):
        store.seed_book(s, root=tmp_path)
