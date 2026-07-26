"""TRIAL-TSMOM-XA lane tests — the seed-a-lane checklist:
hash isolation, no-op-pre-seed, idempotent double-seed, registry-on-seed,
frozen controls untouched, frozen signal correctness, monthly cadence,
refuse-on-missing-price, signed booking."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.config import tsmom_xa_lanes
from backend.db import (
    get_book_config_hash,
    get_config_hash,
    get_connection,
    get_conservative_atr_config_hash,
    get_smq_config_hash,
    get_tsmom_config_hash,
    init_db,
)
from backend.services.portfolio_intelligence.nav import CASH_TICKER
from backend.services.portfolio_intelligence.tsmom_lane import (
    CONTROL_LANE,
    OVERLAY_LANE,
    compute_sleeve_weights,
    control_target,
    mark_all_tsmom_lanes,
    overlay_target,
    run_tsmom_check,
    seed_tsmom_lanes,
)

PRICES = {"SPY": 500.0, "TLT": 90.0, "GLD": 220.0, "USO": 75.0}


def _panel(n=320, up=("SPY", "GLD"), down=("TLT", "USO"), end="2026-07-24"):
    """Synthetic close panel: clean up/down trends, mild noise for vol."""
    idx = pd.bdate_range(end=end, periods=n)
    rng = np.random.default_rng(3)
    data = {}
    for a in (*up, *down):
        drift = 0.0008 if a in up else -0.0008
        rets = drift + 0.008 * rng.standard_normal(n)
        data[a] = PRICES[a] * np.exp(np.cumsum(rets))
    return pd.DataFrame(data, index=idx)


class TestConfigIsolation:
    def test_yaml_loads_two_lanes(self):
        assert set(k for k, v in tsmom_xa_lanes.items()
                   if isinstance(v, dict) and "purpose" in v) == {
            OVERLAY_LANE, CONTROL_LANE}

    def test_hash_isolated_from_every_other_config(self):
        h = get_tsmom_config_hash()
        assert h not in {get_config_hash(), get_book_config_hash(),
                         get_conservative_atr_config_hash(),
                         get_smq_config_hash()}


class TestFrozenSignal:
    def test_signs_follow_trends(self):
        sleeve, detail = compute_sleeve_weights(_panel(), date(2026, 7, 24))
        assert sleeve["SPY"] > 0 and sleeve["GLD"] > 0
        assert sleeve["TLT"] < 0 and sleeve["USO"] < 0
        assert detail["n_active"] == 4

    def test_sizing_capped_and_ew_divided(self):
        cfg = tsmom_xa_lanes[OVERLAY_LANE]
        sleeve, _ = compute_sleeve_weights(_panel(), date(2026, 7, 24))
        cap_per_asset = cfg["leverage_cap"] / len(sleeve)
        for w in sleeve.values():
            assert abs(w) <= cap_per_asset + 1e-12

    def test_signal_from_prior_month_end(self):
        _, detail = compute_sleeve_weights(_panel(), date(2026, 7, 24))
        assert detail["month_end"].startswith("2026-06")

    def test_short_panel_raises(self):
        with pytest.raises(ValueError):
            compute_sleeve_weights(_panel(n=120), date(2026, 7, 24))

    def test_overlay_cash_balances_to_one(self):
        sleeve, _ = compute_sleeve_weights(_panel(), date(2026, 7, 24))
        target = overlay_target(sleeve)
        assert sum(target.values()) == pytest.approx(1.0)
        assert target["SPY"] > 0.5 - 1e-9          # core + positive sleeve leg
        assert target[CASH_TICKER] > 0             # short proceeds raise cash

    def test_control_is_frozen_6040(self):
        assert control_target() == {"SPY": 0.6, "TLT": 0.4}


class TestSeedAndLifecycle:
    def _seed(self, tmp_path):
        db = tmp_path / "tsmom.db"
        init_db(db)
        return db, seed_tsmom_lanes(db_path=db, prices=dict(PRICES),
                                    panel=_panel())

    def test_seed_creates_both_lanes_with_isolated_hash(self, tmp_path):
        db, res = self._seed(tmp_path)
        assert res["lanes"][OVERLAY_LANE]["seeded"]
        assert res["lanes"][CONTROL_LANE]["seeded"]
        conn = get_connection(db)
        rows = {r["id"]: r for r in conn.execute(
            "SELECT id, config_version, inception_value FROM paper_portfolios"
        ).fetchall()}
        conn.close()
        assert set(rows) == {OVERLAY_LANE, CONTROL_LANE}
        for r in rows.values():
            assert r["config_version"] == get_tsmom_config_hash()
            assert r["inception_value"] == 100_000.0

    def test_shorts_booked_as_negative_shares(self, tmp_path):
        db, res = self._seed(tmp_path)
        conn = get_connection(db)
        pos = {r["ticker"]: r["shares"] for r in conn.execute(
            "SELECT ticker, shares FROM paper_positions "
            "WHERE portfolio_id = ? AND closed_at IS NULL", (OVERLAY_LANE,),
        ).fetchall()}
        conn.close()
        assert pos["TLT"] < 0 and pos["USO"] < 0   # downtrends → short legs
        assert pos["SPY"] > 0 and pos[CASH_TICKER] > 0
        # book values to notional
        value = sum(n * PRICES.get(t, 1.0) for t, n in pos.items())
        assert value == pytest.approx(100_000.0)

    def test_double_seed_idempotent_and_registry_rows(self, tmp_path):
        db, _ = self._seed(tmp_path)
        res2 = seed_tsmom_lanes(db_path=db, prices=dict(PRICES), panel=_panel())
        assert res2["lanes"][OVERLAY_LANE] == {"seeded": False,
                                               "reason": "already_exists"}
        conn = get_connection(db)
        n_lanes = conn.execute(
            "SELECT COUNT(*) AS n FROM paper_portfolios").fetchone()["n"]
        trials = [r["param"] for r in conn.execute(
            "SELECT param FROM rule_experiments").fetchall()]
        conn.close()
        assert n_lanes == 2                        # no duplicates
        assert f"lane:{OVERLAY_LANE}" in trials
        assert f"lane:{CONTROL_LANE}" in trials
        assert sum(t == f"lane:{OVERLAY_LANE}" for t in trials) == 1

    def test_seed_refuses_on_missing_price(self, tmp_path):
        db = tmp_path / "tsmom2.db"
        init_db(db)
        bad = dict(PRICES)
        bad.pop("GLD")
        with pytest.raises(ValueError, match="REFUSED"):
            seed_tsmom_lanes(db_path=db, prices=bad, panel=_panel())

    def test_other_lanes_untouched_by_seed(self, tmp_path):
        db = tmp_path / "tsmom3.db"
        init_db(db)
        conn = get_connection(db)
        conn.execute(
            "INSERT INTO paper_portfolios (id, inception_date, inception_value, "
            "config_version) VALUES ('conservative', '2026-06-08', 100000.0, 'refhash')",
        )
        conn.commit()
        conn.close()
        seed_tsmom_lanes(db_path=db, prices=dict(PRICES), panel=_panel())
        conn = get_connection(db)
        row = conn.execute(
            "SELECT config_version, inception_date FROM paper_portfolios "
            "WHERE id = 'conservative'").fetchone()
        conn.close()
        assert row["config_version"] == "refhash"
        assert row["inception_date"] == "2026-06-08"


class TestDailyCheck:
    def test_noop_until_seeded(self, tmp_path):
        db = tmp_path / "t4.db"
        init_db(db)
        out = run_tsmom_check(db_path=db, panel=_panel(), prices=dict(PRICES))
        assert out[OVERLAY_LANE] == {"status": "not_seeded"}
        assert mark_all_tsmom_lanes(db_path=db) == {OVERLAY_LANE: None,
                                                    CONTROL_LANE: None}

    def test_same_month_holds_new_month_rebalances(self, tmp_path):
        db = tmp_path / "t5.db"
        init_db(db)
        seed_tsmom_lanes(db_path=db, prices=dict(PRICES), panel=_panel())
        # same calendar month as the seed → hold
        out = run_tsmom_check(db_path=db, as_of_date=date.today(),
                              panel=_panel(), prices=dict(PRICES))
        assert out[OVERLAY_LANE]["status"] == "hold"
        # first check of a new month → rebalance both lanes
        nxt = (date.today().replace(day=1) + pd.offsets.MonthBegin(1)).date()
        panel2 = _panel(end=nxt - pd.Timedelta(days=1))
        out2 = run_tsmom_check(db_path=db, as_of_date=nxt, panel=panel2,
                               prices=dict(PRICES))
        assert out2[OVERLAY_LANE]["status"] == "rebalanced"
        assert out2[CONTROL_LANE]["status"] == "rebalanced"

    def test_missing_price_holds_loudly(self, tmp_path):
        db = tmp_path / "t6.db"
        init_db(db)
        seed_tsmom_lanes(db_path=db, prices=dict(PRICES), panel=_panel())
        nxt = (date.today().replace(day=1) + pd.offsets.MonthBegin(1)).date()
        bad = dict(PRICES)
        bad["USO"] = None
        panel2 = _panel(end=nxt - pd.Timedelta(days=1))
        out = run_tsmom_check(db_path=db, as_of_date=nxt, panel=panel2,
                              prices=bad)
        assert out[OVERLAY_LANE]["status"] == "hold"
        assert "prices_missing" in out[OVERLAY_LANE]["reason"]

    def test_rebalance_value_neutral_with_shorts(self, tmp_path):
        """The P0 invariant, for a SIGNED book: after a forced rebalance at
        moved prices, the book's value equals the pre-rebalance marked value
        minus costs."""
        db = tmp_path / "t7.db"
        init_db(db)
        seed_tsmom_lanes(db_path=db, prices=dict(PRICES), panel=_panel())
        moved = {t: p * 1.05 for t, p in PRICES.items()}
        conn = get_connection(db)
        pre = {r["ticker"]: r["shares"] for r in conn.execute(
            "SELECT ticker, shares FROM paper_positions WHERE portfolio_id=? "
            "AND closed_at IS NULL", (OVERLAY_LANE,)).fetchall()}
        conn.close()
        pre_value = sum(n * (moved.get(t) or 1.0) for t, n in pre.items())

        out = run_tsmom_check(db_path=db, as_of_date=date.today(),
                              panel=_panel(), prices=moved,
                              force_reason="test_forced")
        assert out[OVERLAY_LANE]["status"] == "rebalanced"
        conn = get_connection(db)
        post = {r["ticker"]: r["shares"] for r in conn.execute(
            "SELECT ticker, shares FROM paper_positions WHERE portfolio_id=? "
            "AND closed_at IS NULL", (OVERLAY_LANE,)).fetchall()}
        conn.close()
        post_value = sum(n * (moved.get(t) or 1.0) for t, n in post.items())
        assert post_value <= pre_value                     # only costs leak
        assert post_value == pytest.approx(pre_value, rel=2e-3)
