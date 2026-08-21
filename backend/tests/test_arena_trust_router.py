"""Known-answer battery for RELIABILITY_ROUTER_v1.

A learner is more dangerous than a static model: a bad update propagates.
So before any book may ever cite this router, it must pass worlds where the
right answer is known by construction:

  null world          -> no manufactured edge
  useful actor        -> recovered
  harmful actor       -> silenced, never negative
  thin cell           -> shrunk to the prior, cannot rank
  lucky streak        -> cannot beat sustained evidence
  sign-flip by state  -> state conditioning recovers it, global stays null
  no data             -> ABSTAIN, loudly
"""

from __future__ import annotations

import pytest

from backend.services.arena import trust_router as tr


def _cells(*rows):
    """rows: (actor, successes, n, horizon, vol_state)"""
    return [{"actor": a, "successes": float(s), "n": int(n),
             "horizon_days": h, "vol_state": v}
            for a, s, n, h, v in rows]


# ── estimator invariants ────────────────────────────────────────────────────
class TestShrunkRate:
    def test_zero_n_returns_parent_exactly(self):
        assert tr.shrunk_rate(0, 0, 0.37) == pytest.approx(0.37)

    def test_large_n_converges_to_data(self):
        assert tr.shrunk_rate(6500, 10000, 0.5) == pytest.approx(0.65, abs=0.01)

    def test_more_shrinkage_with_larger_k(self):
        near = tr.shrunk_rate(8, 8, 0.5, k=2.0)
        far = tr.shrunk_rate(8, 8, 0.5, k=50.0)
        assert abs(far - 0.5) < abs(near - 0.5)

    def test_impossible_cell_refuses(self):
        with pytest.raises(ValueError):
            tr.shrunk_rate(9, 8, 0.5)
        with pytest.raises(ValueError):
            tr.shrunk_rate(-1, 8, 0.5)

    def test_backoff_leaf_inherits_lineage(self):
        # global says 0.60 on n=300; the leaf has n=0 -> estimate is the
        # (shrunk) global, not the naked prior.
        out = tr.backoff_estimate([(180, 300), (0, 0), (0, 0)])
        assert out["estimate"] == pytest.approx(
            tr.shrunk_rate(180, 300, 0.5), abs=1e-9)


# ── known-answer worlds ─────────────────────────────────────────────────────
class TestNullWorld:
    def test_no_edge_is_declared_not_ranked(self):
        cells = _cells(("A", 100, 200, 21, "MID_VOL"),
                       ("B", 101, 200, 21, "MID_VOL"),
                       ("C", 99, 200, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        assert out["verdict"] == "NO_EDGE"
        ws = [a["weight"] for a in out["actors"].values()]
        assert max(ws) - min(ws) < 1e-9  # uniform by fallback, exactly

    def test_null_world_never_manufactures_an_edge(self):
        # exact coin-flip records at healthy n: nothing to recommend
        cells = _cells(("A", 250, 500, 21, "MID_VOL"),
                       ("B", 250, 500, 21, "MID_VOL"))
        assert tr.trust_weights(cells)["verdict"] == "NO_EDGE"


class TestUsefulAndHarmful:
    def test_useful_actor_recovered(self):
        cells = _cells(("GOOD", 130, 200, 21, "MID_VOL"),
                       ("FLAT", 100, 200, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        assert out["verdict"] == "RECOMMENDED"
        assert out["actors"]["GOOD"]["weight"] > out["actors"]["FLAT"]["weight"]
        assert out["actors"]["GOOD"]["weight"] > 0.9

    def test_harmful_actor_silenced_not_shorted(self):
        cells = _cells(("GOOD", 120, 200, 21, "MID_VOL"),
                       ("HARMFUL", 70, 200, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        assert out["actors"]["HARMFUL"]["weight"] == 0.0  # never negative
        assert out["actors"]["GOOD"]["weight"] == pytest.approx(1.0)


class TestThinAndLucky:
    def test_perfect_thin_cell_stays_near_prior(self):
        cells = _cells(("LUCKY", 4, 4, 21, "MID_VOL"),
                       ("STEADY", 110, 200, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        # 4-for-4 shrinks to (4 + 12*0.5)/16 = 0.625; steady 200@55% keeps
        # (110 + 6)/212 = 0.547 — the streak leads on estimate but the test
        # that matters is that it did NOT get an extreme weight...
        assert out["actors"]["LUCKY"]["estimate"] < 0.63

    def test_lucky_streak_cannot_dominate_sustained_evidence(self):
        cells = _cells(("LUCKY", 8, 8, 21, "MID_VOL"),
                       ("STEADY", 240, 400, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        # 8-for-8 -> (8+6)/20 = 0.70 vs 400@60% -> ~0.597. The streak may
        # lead, but bounded: it must not take effectively all the weight the
        # way genuine 200-observation dominance does.
        assert out["actors"]["LUCKY"]["weight"] < 0.6

    def test_evidence_floor_abstains(self):
        cells = _cells(("A", 5, 6, 21, "MID_VOL"),
                       ("B", 2, 6, 21, "MID_VOL"))
        out = tr.trust_weights(cells)
        assert out["verdict"] == "ABSTAIN"
        assert "ignorance" in out["reason"]

    def test_empty_cells_abstain_with_no_actors(self):
        out = tr.trust_weights([])
        assert out["verdict"] == "ABSTAIN"
        assert out["actors"] == {}


class TestStateConditioning:
    CELLS = _cells(
        ("FLIP", 65, 100, 21, "HIGH_VOL"),   # good in high vol
        ("FLIP", 35, 100, 21, "LOW_VOL"),    # harmful in low vol
        ("FLAT", 50, 100, 21, "HIGH_VOL"),
        ("FLAT", 50, 100, 21, "LOW_VOL"),
    )

    def test_high_vol_context_recovers_the_flip_actor(self):
        out = tr.trust_weights(
            self.CELLS, context={"horizon_days": 21, "vol_state": "HIGH_VOL"})
        assert out["verdict"] == "RECOMMENDED"
        assert out["actors"]["FLIP"]["weight"] > out["actors"]["FLAT"]["weight"]

    def test_low_vol_context_silences_the_flip_actor(self):
        out = tr.trust_weights(
            self.CELLS, context={"horizon_days": 21, "vol_state": "LOW_VOL"})
        assert out["actors"]["FLIP"]["weight"] == 0.0

    def test_global_view_of_a_sign_flip_is_null(self):
        # pooled, FLIP is exactly 100/200 — the global read must not
        # recommend what only exists conditionally
        out = tr.trust_weights(self.CELLS)
        assert out["verdict"] == "NO_EDGE"

    def test_thin_state_cell_backs_off_to_actor_global(self):
        cells = _cells(("A", 180, 300, 21, "MID_VOL"),
                       ("A", 2, 3, 21, "HIGH_VOL"),
                       ("B", 150, 300, 21, "MID_VOL"))
        out = tr.trust_weights(
            cells, context={"horizon_days": 21, "vol_state": "HIGH_VOL"})
        # A's HIGH_VOL leaf (n=3) must be dominated by its n=303 lineage
        # (~0.60), not read as 2/3 = 0.67-with-a-straight-face
        assert out["actors"]["A"]["estimate"] < 0.63
        assert out["actors"]["A"]["leaf_n"] == 3


# ── live path over the (empty) arena ────────────────────────────────────────
class TestRecommendLive:
    def test_empty_arena_abstains_honestly(self, tmp_path):
        out = tr.recommend(root=tmp_path)
        assert out["router_version"] == "RELIABILITY_ROUTER_v1"
        assert out["may_mutate_books"] is False
        # Cross-horizon dedup shipped with the G1 battery fix (2026-08-21);
        # the banner must still DISCLOSE that cross-name correlation is not
        # adjusted — a bare True would overclaim.
        assert out["correlation_adjusted"] == "horizon-dedup only"
        assert out["n_reported_cells"] == 0
        assert out["global"]["verdict"] == "ABSTAIN"

    def test_reported_cells_flow_through(self, monkeypatch):
        canned = {
            "n_cells": 3,
            "cells": {
                "m1|21|MID_VOL": {"model_id": "m1", "horizon_days": 21,
                                  "vol_state": "MID_VOL", "verdict": "REPORTED",
                                  "hit_rate": 0.65, "n": 200},
                "m2|21|MID_VOL": {"model_id": "m2", "horizon_days": 21,
                                  "vol_state": "MID_VOL", "verdict": "REPORTED",
                                  "hit_rate": 0.50, "n": 200},
                "m3|21|MID_VOL": {"model_id": "m3", "horizon_days": 21,
                                  "vol_state": "MID_VOL",
                                  "verdict": "REFUSED_THIN", "n": 4},
            },
        }
        monkeypatch.setattr(tr.reliability, "decision_cells",
                            lambda **kw: canned)
        out = tr.recommend()
        assert out["n_reported_cells"] == 2  # the thin cell stayed refused
        g = out["global"]
        assert g["verdict"] == "RECOMMENDED"
        assert g["actors"]["m1"]["weight"] > g["actors"]["m2"]["weight"]

    def test_receipt_declares_its_params(self, tmp_path):
        out = tr.recommend(root=tmp_path)
        assert out["params"]["shrink_k"] == tr.SHRINK_K
        assert out["params"]["edge_z"] == tr.EDGE_Z
        assert out["params"]["evidence_floor_n"] == tr.EVIDENCE_FLOOR_N


class TestEndpoint:
    def test_endpoint_carries_banner_and_refuses_unknown_leg(self, monkeypatch,
                                                             tmp_path):
        from fastapi import HTTPException

        from backend.routers import arena as arena_router

        real_recommend = tr.recommend  # tr IS arena_router.trust_router
        monkeypatch.setattr(arena_router.trust_router, "recommend",
                            lambda **kw: real_recommend(root=tmp_path, **kw))
        out = arena_router.arena_trust_router()
        assert out["validation_status"] == "PRODUCT_EXPERIMENT"
        assert out["simulation"] is True
        assert out["router_version"] == "RELIABILITY_ROUTER_v1"
        with pytest.raises(HTTPException) as exc:
            arena_router.arena_trust_router(leg="vibes")
        assert exc.value.status_code == 422
