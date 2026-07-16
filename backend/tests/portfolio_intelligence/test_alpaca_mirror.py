"""Alpaca paper mirror — verification-infrastructure contract.

All offline (Alpaca API fully mocked). Under test:
- hard no-ops without keys / without the seed flag (a normal deploy can
  never touch Alpaca)
- refuses any non-paper base URL (belt-and-braces against live trading)
- whole-share scaling math
- seed is idempotent (existing positions => never re-seeds) and registers
  the infrastructure annotation
- sync trades ONLY when the internal position set changed, and always
  records third-party equity + divergence into the PIT store
"""

import pytest
from unittest.mock import patch

from backend.services.portfolio_intelligence import alpaca_mirror as am


@pytest.fixture
def tmp_db(tmp_path):
    from backend.db import init_db
    db = tmp_path / "test_pi.db"
    init_db(db)
    return db


def _seed_internal(db, positions, nav=100_000.0):
    from backend.db import get_connection
    conn = get_connection(db)
    conn.execute(
        "INSERT OR IGNORE INTO paper_portfolios (id, inception_date, inception_value, config_version) "
        "VALUES ('mirror', '2026-06-16', 100000.0, 'book')",
    )
    for t, sh in positions.items():
        conn.execute(
            "INSERT INTO paper_positions (portfolio_id, ticker, shares, cost_basis, opened_at) "
            "VALUES ('mirror', ?, ?, 100.0, '2026-06-16')", (t, sh),
        )
    conn.execute(
        "INSERT INTO paper_nav (portfolio_id, date, nav, config_version, computed_at) "
        "VALUES ('mirror', '2026-07-15', ?, 'book', '2026-07-15T20:30:00')", (nav,),
    )
    conn.commit()
    conn.close()


class TestGuards:
    def test_no_keys_means_not_configured(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        assert am.sync_alpaca_mirror()["status"] == "not_configured"

    def test_seed_requires_flag(self, monkeypatch):
        monkeypatch.delenv("AEGIS_SEED_ALPACA_MIRROR", raising=False)
        assert am.seed_alpaca_mirror()["status"] == "not_enabled"

    def test_refuses_non_paper_base(self, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
        monkeypatch.setenv("ALPACA_PAPER_BASE", "https://api.alpaca.markets")
        with pytest.raises(RuntimeError, match="non-paper"):
            am._request("GET", "/v2/account")


class TestScaling:
    def test_whole_share_floor(self):
        targets = am._target_share_counts(
            internal={"AAPL": 100.0, "XOM": 33.3},
            equity=50_000.0, internal_nav=100_000.0,
            prices={"AAPL": 200.0, "XOM": 100.0},
        )
        assert targets == {"AAPL": 50, "XOM": 16}  # floors, residual to cash

    def test_zero_nav_returns_empty(self):
        assert am._target_share_counts({"AAPL": 10}, 1000, 0, {"AAPL": 1}) == {}


class TestSeedAndSync:
    def _mock_api(self, calls, positions=None, equity=100_000.0):
        def fake(method, path, payload=None):
            calls.append((method, path, payload))
            if path == "/v2/positions" and method == "GET":
                return positions or []
            if path == "/v2/account":
                return {"equity": str(equity), "cash": str(equity), "status": "ACTIVE"}
            if path == "/v2/orders":
                return {"id": "o1"}
            return None
        return fake

    def test_seed_places_orders_and_registers(self, tmp_db, monkeypatch):
        monkeypatch.setenv("AEGIS_SEED_ALPACA_MIRROR", "1")
        monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
        _seed_internal(tmp_db, {"AAPL": 100.0, "XOM": 50.0})
        calls = []
        with patch.object(am, "_request", side_effect=self._mock_api(calls)), \
             patch.object(am, "_latest_prices",
                          return_value={"AAPL": 200.0, "XOM": 100.0}):
            out = am.seed_alpaca_mirror(db_path=tmp_db)
        assert out["status"] == "seeded"
        assert {o["symbol"] for o in out["orders"]} == {"AAPL", "XOM"}
        # registry annotation landed
        from backend.db import get_connection
        conn = get_connection(tmp_db)
        row = conn.execute("SELECT param FROM rule_experiments WHERE param = ?",
                           (am.TRIAL_PARAM,)).fetchone()
        conn.close()
        assert row is not None

    def test_seed_idempotent_on_existing_positions(self, tmp_db, monkeypatch):
        monkeypatch.setenv("AEGIS_SEED_ALPACA_MIRROR", "1")
        monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
        calls = []
        existing = [{"symbol": "AAPL", "qty": "50", "current_price": "200"}]
        with patch.object(am, "_request",
                          side_effect=self._mock_api(calls, positions=existing)):
            out = am.seed_alpaca_mirror(db_path=tmp_db)
        assert out["status"] == "already_seeded"
        assert not any(p == "/v2/orders" for _, p, _ in calls)

    def test_sync_no_trades_when_position_set_unchanged(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
        _seed_internal(tmp_db, {"AAPL": 100.0}, nav=101_000.0)
        calls = []
        held = [{"symbol": "AAPL", "qty": "100", "current_price": "200"}]
        with patch.object(am, "_request",
                          side_effect=self._mock_api(calls, positions=held,
                                                     equity=100_500.0)):
            out = am.sync_alpaca_mirror(db_path=tmp_db)
        assert out["status"] == "synced"
        assert out["trades"] == []
        # divergence recorded: (100500/100000 - 101000/100000)*100 = -0.5
        assert out["divergence_pct"] == -0.5
        # third-party equity persisted to the PIT store
        st = am.alpaca_mirror_status(db_path=tmp_db)
        assert st["recorded"] is True
        assert st["equity"] == 100_500.0

    def test_sync_follows_internal_rebalance(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
        _seed_internal(tmp_db, {"MSFT": 100.0})  # internal moved AAPL -> MSFT
        calls = []
        held = [{"symbol": "AAPL", "qty": "100", "current_price": "200"}]
        with patch.object(am, "_request",
                          side_effect=self._mock_api(calls, positions=held)), \
             patch.object(am, "_latest_prices", return_value={"MSFT": 400.0}):
            out = am.sync_alpaca_mirror(db_path=tmp_db)
        actions = {(t["symbol"], t["action"]) for t in out["trades"]}
        assert ("AAPL", "close") in actions
        assert ("MSFT", "open") in actions
