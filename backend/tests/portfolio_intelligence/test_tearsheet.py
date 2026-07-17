"""
Tests for the lane tearsheet + bootstrap-CI rigor layer (V4).

Offline throughout: synthetic returns, tmp SQLite for paper_nav reads,
quantstats rendered benchmark-free (the network-blocked conftest would
catch any yfinance leak from quantstats' own utilities).
"""

import numpy as np
import pytest

from backend.db import get_connection, init_db
from backend.services.portfolio_intelligence.tearsheet import (
    MIN_OBS,
    bootstrap_stat_cis,
    lane_return_series,
    lane_stats_with_cis,
    lane_tearsheet_html,
)


def _synthetic_returns(n=252, mu=0.0004, sigma=0.01, seed=7):
    rng = np.random.default_rng(seed)
    return rng.normal(mu, sigma, n)


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "tearsheet.db"
    init_db(p)
    return p


def _seed_lane_nav(db_path, lane_id="balanced", n=60, seed=7):
    """Insert a synthetic paper_nav path (read-path test double — the real
    write path is never exercised here)."""
    import pandas as pd

    rets = _synthetic_returns(n=n, seed=seed)
    nav = 100_000.0 * np.cumprod(1 + rets)
    dates = pd.bdate_range("2026-01-02", periods=n).strftime("%Y-%m-%d")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO paper_portfolios "
            "(id, inception_date, inception_value, config_version) "
            "VALUES (?, ?, ?, ?)",
            (lane_id, dates[0], 100_000.0, "testhash"),
        )
        conn.executemany(
            "INSERT INTO paper_nav (portfolio_id, date, nav, config_version, "
            "computed_at) VALUES (?, ?, ?, ?, ?)",
            [(lane_id, d, float(v), "testhash", d) for d, v in zip(dates, nav)],
        )
        conn.commit()
    finally:
        conn.close()
    return rets


class TestBootstrapCIs:
    def test_ci_brackets_point_estimate(self):
        pack = bootstrap_stat_cis(_synthetic_returns())
        assert pack["status"] == "ok"
        for name in ("sharpe", "sortino"):
            s = pack["stats"][name]
            assert s["ci_lo"] is not None and s["ci_hi"] is not None
            assert s["ci_lo"] <= s["value"] <= s["ci_hi"]
            assert s["method"] in ("BCa", "percentile")

    def test_maxdd_ci_is_negative_and_ordered(self):
        pack = bootstrap_stat_cis(_synthetic_returns())
        mdd = pack["stats"]["max_drawdown"]
        assert mdd["value"] <= 0
        assert mdd["ci_lo"] <= mdd["ci_hi"] <= 0
        assert mdd["method"] == "circular_block_percentile"

    def test_deterministic_with_seed(self):
        r = _synthetic_returns()
        assert bootstrap_stat_cis(r) == bootstrap_stat_cis(r)

    def test_insufficient_history(self):
        pack = bootstrap_stat_cis(_synthetic_returns(n=MIN_OBS - 1))
        assert pack["status"] == "insufficient_history"
        assert pack["stats"] is None

    def test_zero_variance_does_not_crash(self):
        pack = bootstrap_stat_cis(np.zeros(60))
        assert pack["status"] == "ok"
        assert pack["stats"]["sharpe"]["value"] == 0.0

    def test_all_positive_returns_sortino_undefined(self):
        # no downside observations → Sortino is undefined (inf), not a number
        pack = bootstrap_stat_cis(np.full(40, 0.001))
        assert pack["stats"]["sortino"]["value"] is None
        assert pack["stats"]["sortino"]["method"] == "undefined"

    def test_wide_ci_on_short_history(self):
        # 25 observations → the interval must be honest, i.e. WIDE
        pack = bootstrap_stat_cis(_synthetic_returns(n=25))
        s = pack["stats"]["sharpe"]
        assert (s["ci_hi"] - s["ci_lo"]) > 1.0


class TestLaneReturnSeries:
    def test_reads_paper_nav(self, db_path):
        _seed_lane_nav(db_path, n=60)
        rets = lane_return_series("balanced", db_path=db_path)
        assert rets is not None and len(rets) == 59

    def test_unseeded_lane_returns_none(self, db_path):
        assert lane_return_series("balanced", db_path=db_path) is None

    def test_stats_pack_from_db(self, db_path):
        _seed_lane_nav(db_path, n=60)
        pack = lane_stats_with_cis("balanced", db_path=db_path)
        assert pack["status"] == "ok"
        assert pack["lane_id"] == "balanced"
        assert pack["n_obs"] == 59
        assert pack["first_date"] < pack["last_date"]

    def test_stats_pack_unseeded(self, db_path):
        pack = lane_stats_with_cis("mirror", db_path=db_path)
        assert pack["status"] == "insufficient_history" and pack["n_obs"] == 0


class TestTearsheetHtml:
    def test_renders_html_with_banner(self, db_path):
        _seed_lane_nav(db_path, n=60)
        html = lane_tearsheet_html("balanced", db_path=db_path,
                                   include_benchmark=False)
        assert "<html" in html.lower()
        assert "balanced" in html
        assert "paper" in html  # the honesty banner
        assert "No skill claims before 24 months" in html
        assert len(html) > 10_000

    def test_insufficient_history_raises(self, db_path):
        _seed_lane_nav(db_path, n=3)
        with pytest.raises(ValueError, match="insufficient"):
            lane_tearsheet_html("balanced", db_path=db_path,
                                include_benchmark=False)


class TestRouterValidation:
    def test_unknown_lane_404(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/api/pi/lane/not-a-lane/stats-ci").status_code == 404
        assert client.get("/api/pi/lane/not-a-lane/tearsheet").status_code == 404
