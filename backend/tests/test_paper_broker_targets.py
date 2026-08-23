"""The paper broker must mirror a DECLARED source, and must never guess.

Two things are under test, and the second one is a real incident.

1. **Target resolution.** The adapter used to be hard-wired to the legacy
   `mirror` lane, so the arena's ten decision-making books could not reach the
   external paper account at all. Targets fix that -- without silently
   repointing the lane that already has a third-party-verified history.

2. **The empty-source refusal.** `sync` reads positions from a LOCAL source and
   executes against a SHARED remote account. An unreadable source and a
   genuinely flat source are indistinguishable, and the old code resolved that
   ambiguity by closing the entire book.

   Paid for on 2026-08-23: a smoke-test call to `sync_alpaca_mirror()` from the
   dev machine placed 12 real sell orders against the live paper account,
   because the local SQLite DB has no `mirror` lane rows. The orders were
   accepted-not-filled (Sunday, market closed) and were cancelled before the
   open. Nothing was lost -- by luck of the clock, not by any check. These
   tests are the check.

Every test here drives a FAKE transport. Nothing in this file may ever reach a
real Alpaca host.
"""

from __future__ import annotations

import pytest

from backend.services.portfolio_intelligence import alpaca_mirror as AM
from backend.services.portfolio_intelligence import paper_broker_targets as T


# ------------------------------------------------------------ target parsing


def test_default_target_is_the_legacy_lane(monkeypatch):
    monkeypatch.delenv(T.TARGET_ENV, raising=False)
    t = T.parse_target()
    assert t.target_id == "lane:mirror"
    assert t.is_legacy_lane


def test_legacy_lane_keeps_its_original_pit_keys(monkeypatch):
    """Renaming these would orphan the equity history the adapter records."""
    monkeypatch.delenv(T.TARGET_ENV, raising=False)
    t = T.parse_target()
    assert t.equity_key == "alpaca:equity"
    assert t.state_key == "alpaca:mirror_state"
    assert t.trial_param == "alpaca-mirror-verification"


def test_arena_book_is_a_valid_target():
    t = T.parse_target("arena:CURRENT_BEST_v1")
    assert t.kind == "arena"
    assert t.source_id == "CURRENT_BEST_v1"
    assert not t.is_legacy_lane


def test_arena_target_namespaces_its_keys_away_from_the_lane():
    lane = T.parse_target("lane:mirror")
    arena = T.parse_target("arena:CURRENT_BEST_v1")
    assert arena.equity_key != lane.equity_key
    assert arena.state_key != lane.state_key


@pytest.mark.parametrize("bad", ["nonsense", "weird:X", "arena:", "lane:", ":x"])
def test_unknown_target_is_refused_never_defaulted(bad):
    """A typo that silently mirrored the wrong book would corrupt a record."""
    with pytest.raises(T.UnknownTarget):
        T.parse_target(bad)


def test_env_declares_the_target(monkeypatch):
    monkeypatch.setenv(T.TARGET_ENV, "arena:LLM_EVENTS_v1")
    assert T.parse_target().source_id == "LLM_EVENTS_v1"


# ------------------------------------------------- per-target credentials


def test_the_legacy_lane_keeps_its_original_env_vars(monkeypatch):
    """Renaming these would silently unconfigure a live integration."""
    assert T.parse_target("lane:mirror").key_env == (
        "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")


def test_an_arena_book_needs_its_OWN_credentials():
    assert T.parse_target("arena:CURRENT_BEST_v1").key_env == (
        "ALPACA_ARENA_API_KEY_ID", "ALPACA_ARENA_API_SECRET_KEY")


def test_an_arena_book_sharing_the_lanes_ACCOUNT_is_refused(monkeypatch):
    """THE guard. One Alpaca account has one equity curve.

    Pointing an arena book at the mirror lane's account would execute its
    orders into a third-party-verified history going back to inception — the
    only independent check this project has on its own NAV maths — and destroy
    it irreversibly. Falling back to the lane's keys is the permissive
    direction, and the permissive direction here is unrecoverable.
    """
    monkeypatch.setenv("ALPACA_API_KEY_ID", "SHARED")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_ARENA_API_KEY_ID", "SHARED")
    monkeypatch.setenv("ALPACA_ARENA_API_SECRET_KEY", "s")
    with pytest.raises(T.SharedAccountRefused):
        T.credentials(T.parse_target("arena:CURRENT_BEST_v1"))


def test_distinct_accounts_are_accepted(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "LANEKEY")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_ARENA_API_KEY_ID", "ARENAKEY")
    monkeypatch.setenv("ALPACA_ARENA_API_SECRET_KEY", "s2")
    assert T.credentials(T.parse_target("arena:CURRENT_BEST_v1")) == (
        "ARENAKEY", "s2")


def test_an_arena_book_does_NOT_inherit_the_lanes_keys(monkeypatch):
    """Absent arena keys means unconfigured, never 'use the lane's'."""
    monkeypatch.setenv("ALPACA_API_KEY_ID", "LANEKEY")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.delenv("ALPACA_ARENA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_ARENA_API_SECRET_KEY", raising=False)
    assert T.credentials(T.parse_target("arena:CURRENT_BEST_v1")) is None


def test_describe_surfaces_a_shared_account_as_REFUSED(monkeypatch):
    monkeypatch.setenv(T.TARGET_ENV, "arena:CURRENT_BEST_v1")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "SHARED")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_ARENA_API_KEY_ID", "SHARED")
    monkeypatch.setenv("ALPACA_ARENA_API_SECRET_KEY", "s")
    d = T.describe()
    assert d["status"] == "REFUSED"
    assert "one equity curve" in d["credential_error"]


def test_annotation_marks_paper_only():
    a = T.annotation(T.parse_target("arena:CURRENT_BEST_v1"))
    assert a["paper_only"] is True
    assert a["real_capital"] is False


# ------------------------------------------------- arena position/nav reads


def test_arena_positions_read_from_the_book(tmp_path):
    from backend.services.arena import store
    store.write_positions("BOOK_X", {
        "cash": 1000.0,
        "positions": {"AAPL": {"shares": 10.0}, "MSFT": {"shares": 0.0}},
    }, root=tmp_path)
    got = T.positions(T.parse_target("arena:BOOK_X"), root=tmp_path)
    assert got == {"AAPL": 10.0}, "zero-share rows must not be mirrored"


def test_arena_nav_reads_the_latest_mark(tmp_path):
    from backend.services.arena import store
    store.append_nav("BOOK_X", [{"date": "2026-08-20", "nav": 100.0},
                                {"date": "2026-08-21", "nav": 123.0}],
                     root=tmp_path)
    assert T.nav(T.parse_target("arena:BOOK_X"), root=tmp_path) == 123.0


def test_arena_nav_is_None_when_never_marked(tmp_path):
    assert T.nav(T.parse_target("arena:NEW_BOOK"), root=tmp_path) is None


# ------------------------------------------------ THE REFUSAL (the incident)


class _FakeAlpaca:
    """Records every call. Nothing here reaches a network."""

    def __init__(self, positions):
        self.positions = positions
        self.calls: list[tuple] = []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/v2/positions" and method == "GET":
            return [{"symbol": s, "qty": str(q), "current_price": "10.0"}
                    for s, q in self.positions.items()]
        if path == "/v2/account":
            return {"equity": "100000.0", "cash": "0.0"}
        if path.startswith("/v2/orders"):
            return []
        return None

    @property
    def destructive(self) -> list[tuple]:
        return [c for c in self.calls
                if c[0] == "DELETE"
                or (c[0] == "POST" and c[1].startswith("/v2/orders"))]


@pytest.fixture
def fake(monkeypatch):
    f = _FakeAlpaca({"AAPL": 10, "MSFT": 5, "NVDA": 3})
    monkeypatch.setattr(AM, "_request", f)
    monkeypatch.setattr(AM, "alpaca_available", lambda: True)
    monkeypatch.setattr(AM, "_record_equity",
                        lambda *a, **k: None)
    monkeypatch.delenv("AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION", raising=False)
    return f


def test_empty_internal_source_does_NOT_liquidate(fake, monkeypatch):
    """THE incident test. Source reads empty -> refuse, do not close 12 names."""
    monkeypatch.setattr(AM, "_internal_positions", lambda *a, **k: {})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: None)

    out = AM.sync_alpaca_mirror()

    assert out["status"] == "refused_source_empty", out
    assert fake.destructive == [], (
        f"an unreadable source produced live orders: {fake.destructive}")


def test_explicit_flag_re_permits_a_genuine_liquidation(fake, monkeypatch):
    """A book that really went to cash must still be able to say so."""
    monkeypatch.setattr(AM, "_internal_positions", lambda *a, **k: {})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: 100_000.0)
    monkeypatch.setenv("AEGIS_ALPACA_ALLOW_FULL_LIQUIDATION", "1")

    out = AM.sync_alpaca_mirror()
    assert out["status"] != "refused_source_empty"


def test_going_flat_on_a_price_outage_is_refused(fake, monkeypatch):
    """`_target_share_counts` drops any name it has no price for.

    A price-feed outage therefore empties the target book while the internal
    book is perfectly readable — and the account would be liquidated by a data
    failure rather than a decision.
    """
    monkeypatch.setattr(AM, "_internal_positions",
                        lambda *a, **k: {"AAPL": 10.0, "MSFT": 5.0})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: 100_000.0)
    monkeypatch.setattr(AM, "_latest_prices", lambda syms: {})   # outage
    monkeypatch.setattr(AM, "_target_share_counts",
                        lambda *a, **k: {})

    out = AM.sync_alpaca_mirror()
    assert out["status"] == "refused_targets_empty", out
    assert fake.destructive == []


def test_a_rotation_is_NOT_treated_as_a_liquidation(fake, monkeypatch):
    """Closing 100% of a one-name book to open another is a real rebalance.

    An earlier version of this guard keyed on the FRACTION closed and blocked
    exactly this; the existing alpaca_mirror suite caught it. The rule is
    "never end up flat", not "never close a lot".
    """
    fake.positions = {"AAPL": 100}
    monkeypatch.setattr(AM, "_internal_positions", lambda *a, **k: {"MSFT": 5.0})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: 100_000.0)
    monkeypatch.setattr(AM, "_latest_prices", lambda syms: {"MSFT": 400.0})

    out = AM.sync_alpaca_mirror()
    assert out["status"] == "synced", out
    actions = {(t["symbol"], t["action"]) for t in out["trades"]}
    assert ("AAPL", "close") in actions and ("MSFT", "open") in actions


def test_ordinary_rebalance_still_trades(fake, monkeypatch):
    """The guards must not freeze the adapter: a small change still executes."""
    monkeypatch.setattr(AM, "_internal_positions",
                        lambda *a, **k: {"AAPL": 10.0, "MSFT": 5.0,
                                         "GOOG": 4.0})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: 100_000.0)

    out = AM.sync_alpaca_mirror()
    assert out["status"] == "synced", out
    assert fake.destructive, "a genuine rebalance placed no orders at all"


def test_seed_resolves_its_target_after_the_order_loop(fake, monkeypatch,
                                                       tmp_path):
    """Regression: `t` was both the resolved target AND the per-ticker loop
    variable in `seed`, so the loop clobbered it and the registry annotation
    blew up with `'str' object has no attribute 'trial_param'`.

    The bug survived my own tests because they only exercised `sync`, and the
    full suite I checked before pushing had been launched BEFORE these changes
    existed. CI caught it on a clean checkout. Seed is covered now.
    """
    monkeypatch.setenv("AEGIS_SEED_ALPACA_MIRROR", "1")
    monkeypatch.setattr(AM, "_internal_positions",
                        lambda *a, **k: {"AAPL": 10.0, "MSFT": 5.0})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: 100_000.0)
    monkeypatch.setattr(AM, "_latest_prices",
                        lambda syms: {s: 10.0 for s in syms})
    registered = {}
    monkeypatch.setattr(
        "backend.services.portfolio_intelligence.trial_registry"
        ".ensure_trial_registered",
        lambda param, ann, db_path=None: registered.update(
            {"param": param, "ann": ann}))
    # An account with no positions and no open orders is "not yet seeded".
    fake.positions = {}

    out = AM.seed_alpaca_mirror()

    assert out["status"] == "seeded", out
    assert out["target_id"] == "lane:mirror"
    assert registered["param"] == "alpaca-mirror-verification"
    assert registered["ann"]["paper_only"] is True


def test_sync_reports_which_target_it_acted_on(fake, monkeypatch):
    monkeypatch.setattr(AM, "_internal_positions", lambda *a, **k: {})
    monkeypatch.setattr(AM, "_internal_nav", lambda *a, **k: None)
    assert AM.sync_alpaca_mirror()["target_id"] == "lane:mirror"
