"""Personality grading read — declared utilities over realised NAV paths.

The one behavioural claim that matters: the SAME books rank DIFFERENTLY
under different declared utilities, and the declaration itself is pinned so
it cannot drift silently (a changed rho is an attended act, not a refactor).
"""

from __future__ import annotations

import math

import pytest

from backend import config
from backend.services.arena import personality_read as pr
from backend.services.arena import store


@pytest.fixture()
def root(tmp_path):
    return tmp_path / "arena"


def _write_nav(root, book_id, daily_log_returns, start_nav=100000.0):
    nav = start_nav
    rows = []
    for i, r in enumerate(daily_log_returns):
        nav *= math.exp(r)
        rows.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                     "nav": round(nav, 2)})
    store.append_nav(book_id, [{"date": "2025-12-31", "nav": start_nav}],
                     root)
    store.append_nav(book_id, rows, root)


class TestDeclaration:
    def test_the_declared_rhos_are_pinned(self):
        """Changing a personality's risk aversion is an ATTENDED declaration
        change. This test failing is the alarm, not an inconvenience."""
        assert config.ARENA_PERSONALITY_RHO == {
            "preservation": 8.0, "balanced": 4.0,
            "aggressive": 2.0, "extreme_growth": 1.0}
        assert config.ARENA_PERSONALITY_MIN_DAYS == 60

    def test_empty_arena_abstains_per_personality(self, root):
        out = pr.report(root=root)
        assert out["kind"] == "grading_read"
        assert out["may_mutate_books"] is False
        assert out["n_scored"] == 0
        for p in config.ARENA_PERSONALITY_RHO:
            assert out["personalities"][p]["verdict"] == "ABSTAIN"
            assert "objective" in out["personalities"][p]


class TestScoring:
    def test_rankings_flip_across_personalities(self, root):
        """STEADY: ~8%/yr at ~3% vol. WILD: ~30%/yr at ~32% vol.

        Constructed so extreme growth prefers WILD while preservation
        prefers STEADY — the same realised paths, different declared
        preferences, different podium. That flip is the entire point of
        having personalities.
        """
        n = 80
        # STEADY: mean 8%/252 daily, sd 0.2% daily (~3.2% ann vol)
        steady = [0.08 / 252 + (0.002 if i % 2 else -0.002) for i in range(n)]
        # WILD: mean 30%/252 daily, sd 2% daily (~32% ann vol)
        wild = [0.30 / 252 + (0.02 if i % 2 else -0.02) for i in range(n)]
        _write_nav(root, "ENGINE_BASELINE_v1", steady)
        _write_nav(root, "AGGRESSIVE_TOP5_v1", wild)
        out = pr.report(root=root)

        assert out["books"]["ENGINE_BASELINE_v1"]["verdict"] == "SCORED"
        pers = out["personalities"]
        top = {p: pers[p]["ranking"][0]["book_id"]
               for p in config.ARENA_PERSONALITY_RHO}
        # rho=8: wild's variance penalty 0.5*8*0.1 ≈ 0.40 >> its 0.22 extra
        # growth -> STEADY wins preservation
        assert top["preservation"] == "ENGINE_BASELINE_v1"
        # rho=1: penalty 0.5*0.1 = 0.05 << 0.22 extra growth -> WILD wins
        assert top["extreme_growth"] == "AGGRESSIVE_TOP5_v1"
        # and every ranking names its objective
        for p, rho in config.ARENA_PERSONALITY_RHO.items():
            assert f"rho={rho}" in pers[p]["objective"]

    def test_thin_books_refuse_with_their_n(self, root):
        _write_nav(root, "ENGINE_BASELINE_v1", [0.001] * 10)
        out = pr.report(root=root)
        b = out["books"]["ENGINE_BASELINE_v1"]
        assert b["verdict"] == "REFUSED_THIN"
        assert b["n_days"] == 10 and b["min_days"] == 60
        assert "ce_by_personality" not in b

    def test_reported_stats_are_sane(self, root):
        n = 80
        _write_nav(root, "ENGINE_BASELINE_v1",
                   [0.10 / 252 + (0.004 if i % 2 else -0.004)
                    for i in range(n)])
        out = pr.report(root=root)
        b = out["books"]["ENGINE_BASELINE_v1"]
        assert b["ann_log_growth"] == pytest.approx(0.10, abs=0.02)
        assert 0.0 < b["ann_vol"] < 0.15
        assert 0.0 <= b["max_drawdown"] < 0.05

    def test_route_is_registered(self):
        from backend.routers.arena import router
        assert any(r.path == "/api/arena/personalities"
                   for r in router.routes)
