"""
Offline tests for the conservative-ATR lane (TRIAL-EXIT) seed + daily exit-overlay
management. All offline: prices/panels are injected, so no network. Verifies the
load-bearing safety properties the user asked for — hash isolation (cannot touch
the frozen conservative control or the reference lanes), no-op-until-seeded,
registry-on-seed, and that the exit overlay actually fires (stop → rotate to cash).
"""

from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import pytest

from backend.db import (
    get_conservative_atr_config_hash,
    get_book_config_hash,
    get_config_hash,
    get_connection,
    init_db,
)
from backend.services.portfolio_intelligence import exit_lane as el
from backend.services.portfolio_intelligence.exit_lane import LANE_ID, _mandate_tickers
from backend.services.portfolio_intelligence.nav import CASH_TICKER


@pytest.fixture
def db():
    path = Path(tempfile.mkdtemp()) / "exit_lane_test.db"
    init_db(path)
    return path


def _flat_prices() -> dict:
    return {t: 100.0 for t in _mandate_tickers()}


def _noisy_panel(periods=80, seed=0, rollover: str | None = None) -> pd.DataFrame:
    """Full mandate panel with realistic per-name noise (so every name has finite
    vol), ending today. If ``rollover`` is given, that name rises then crashes —
    a textbook ATR trailing-stop trigger."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=periods)
    cols = {}
    for i, t in enumerate(_mandate_tickers()):
        steps = rng.normal(0.0003, 0.01, periods).cumsum()
        cols[t] = 100.0 * np.exp(steps)
    if rollover is not None:
        up = np.linspace(0, 0.6, periods // 2)              # +60% rise
        down = np.linspace(0.6, -0.1, periods - periods // 2)  # then crash through entry
        cols[rollover] = 100.0 * np.exp(np.concatenate([up, down]))
    return pd.DataFrame(cols, index=idx)


class TestHashIsolation:
    def test_atr_hash_distinct_from_reference_and_book(self):
        h_atr = get_conservative_atr_config_hash()
        assert h_atr != get_config_hash()       # never the reference-lane hash
        assert h_atr != get_book_config_hash()  # never the book-lane hash


class TestNoOpUntilSeeded:
    def test_daily_check_no_op_before_seed(self, db):
        assert el.run_exit_overlay_check(db_path=db)["status"] == "not_seeded"

    def test_mtm_skips_unseeded_lane(self, db):
        assert el.mark_all_conservative_atr_lanes(db_path=db) == {LANE_ID: None}


class TestSeed:
    def test_seed_creates_lane_with_isolated_hash(self, db):
        res = el.seed_conservative_atr_lane(db_path=db, prices=_flat_prices(), panel=None)
        assert res["seeded"] is True and res["n_positions"] > 0
        conn = get_connection(db)
        try:
            pp = conn.execute(
                "SELECT config_version FROM paper_portfolios WHERE id = ?", (LANE_ID,)
            ).fetchone()
        finally:
            conn.close()
        assert pp["config_version"] == get_conservative_atr_config_hash()

    def test_seed_is_idempotent(self, db):
        el.seed_conservative_atr_lane(db_path=db, prices=_flat_prices(), panel=None)
        again = el.seed_conservative_atr_lane(db_path=db, prices=_flat_prices(), panel=None)
        assert again["seeded"] is False and again["reason"] == "already_exists"

    def test_seed_registers_trial_with_atr_hash(self, db):
        el.seed_conservative_atr_lane(db_path=db, prices=_flat_prices(), panel=None)
        conn = get_connection(db)
        try:
            row = conn.execute(
                "SELECT config_version, verdict FROM rule_experiments WHERE lane_id = ?",
                (LANE_ID,),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["config_version"] == get_conservative_atr_config_hash()


class TestFrozenControlUntouched:
    def test_seeding_atr_does_not_create_or_touch_conservative(self, db):
        # The frozen `conservative` control must not be created or altered by an
        # ATR seed — the whole point of the separate hash + file.
        el.seed_conservative_atr_lane(db_path=db, prices=_flat_prices(), panel=None)
        conn = get_connection(db)
        try:
            cons = conn.execute(
                "SELECT 1 FROM paper_portfolios WHERE id = 'conservative'"
            ).fetchone()
        finally:
            conn.close()
        assert cons is None  # ATR seed never touches the control lane


class TestExitOverlayFires:
    def test_rolled_over_name_is_stopped_and_rotated_to_cash(self, db):
        prices = _flat_prices()
        el.seed_conservative_atr_lane(db_path=db, prices=prices, panel=None)

        # Backdate every position so there is post-entry history for the stop.
        conn = get_connection(db)
        try:
            old = (pd.Timestamp.today().normalize() - pd.Timedelta(days=120)).date().isoformat()
            conn.execute(
                "UPDATE paper_positions SET opened_at = ? WHERE portfolio_id = ?",
                (old, LANE_ID),
            )
            conn.commit()
            # pick a held equity name to roll over
            held = [r["ticker"] for r in conn.execute(
                "SELECT ticker FROM paper_positions WHERE portfolio_id = ? "
                "AND closed_at IS NULL AND ticker != ?", (LANE_ID, CASH_TICKER)
            ).fetchall()]
        finally:
            conn.close()
        rollover = next(t for t in held if t in _mandate_tickers())
        panel = _noisy_panel(rollover=rollover)

        out = el.run_exit_overlay_check(db_path=db, prices=prices, panel=panel)
        assert out["status"] == "rebalanced"
        assert out["reason"] == "exit_overlay"
        assert rollover in out["stopped"]

        # the stopped name must be flat to zero (rotated to cash) in the new book
        conn = get_connection(db)
        try:
            open_now = {r["ticker"] for r in conn.execute(
                "SELECT ticker FROM paper_positions WHERE portfolio_id = ? "
                "AND closed_at IS NULL", (LANE_ID,)
            ).fetchall()}
        finally:
            conn.close()
        assert rollover not in open_now           # sold out of the stopped name
        assert CASH_TICKER in open_now             # proceeds parked in cash

    def test_no_stop_holds_on_calm_panel(self, db):
        prices = _flat_prices()
        el.seed_conservative_atr_lane(db_path=db, prices=prices, panel=None)
        # fresh seed (entry today) → no post-entry history → no stop → hold
        out = el.run_exit_overlay_check(db_path=db, prices=prices, panel=_noisy_panel())
        assert out["status"] in ("hold", "rebalanced")
        assert out["n_stopped"] == 0
