"""Contract for the ORDER 27 P2 gate on router capital authority.

Three populations of test here, and they answer different questions:

  * `design_effect` — does the counting brain measure clustering correctly on
    inputs whose answer is known by hand?
  * the router's v1.1 path — does the correction change what it claims to
    change, and NOTHING on the v1 path that ORDER 27 froze?
  * the gate — does it refuse every missing input, and can it still say PASS?

The last one matters as much as the refusals: a gate whose PASS is
unreachable is a gate that has stopped measuring and started blocking, and
that failure reads identically to a working gate until the day it costs a
real result (canon §37: assert every verdict reachable).
"""

from __future__ import annotations

import json

import pytest

from backend.services import router_capital_gate as G
from backend.services.arena import reliability, trust_router


# ── design effect ───────────────────────────────────────────────────────────
class TestDesignEffect:
    def test_one_decision_per_day_is_not_deflated(self):
        """Unclustered data must not be penalised: with one decision per day
        there is no day factor to share, so n_effective is the row count."""
        by_day = {f"d{i}": [i % 2] for i in range(40)}
        out = reliability.design_effect(by_day)
        assert out["n_clusters"] == 40
        assert out["deff"] == pytest.approx(1.0, abs=0.35)
        assert out["n_effective"] >= 29

    def test_a_day_that_moves_together_collapses_to_its_days(self):
        """Ten names that share one morning are one morning of information."""
        by_day = {f"d{i}": [1] * 10 if i % 2 else [0] * 10 for i in range(20)}
        out = reliability.design_effect(by_day)
        assert out["n_clusters"] == 20
        assert out["deff"] > 5.0
        # 200 rows, 20 perfectly-correlated days -> ~20 independent decisions
        assert out["n_effective"] <= 25

    def test_a_single_cluster_is_a_single_draw(self):
        out = reliability.design_effect({"d0": [1, 0, 1, 1, 0, 1]})
        assert out["n_effective"] == 1
        assert out["estimated"] is False

    def test_a_degenerate_rate_says_it_did_not_measure(self):
        """All hits: clustering is unmeasurable. The number returned must not
        read like a measurement."""
        out = reliability.design_effect({f"d{i}": [1, 1] for i in range(10)})
        assert out["estimated"] is False
        assert out["deff"] == 1.0

    def test_deff_never_claims_more_information_than_rows(self):
        """Anti-correlated clusters would compute deff < 1. Floored at 1: a
        capital router does not get to claim a larger sample than it has."""
        by_day = {f"d{i}": [0, 1] for i in range(30)}
        assert reliability.design_effect(by_day)["deff"] >= 1.0

    def test_no_rows_is_not_an_answer(self):
        out = reliability.design_effect({})
        assert out["n_effective"] == 0 and out["estimated"] is False


# ── the v1 path ORDER 27 froze ──────────────────────────────────────────────
def _cells(actor: str, hit_rate: float, n: int, clustering=None):
    out = []
    for h in (1, 5, 21, 63, 126):
        for vs in ("LOW_VOL", "MID_VOL", "HIGH_VOL"):
            c = {"actor": actor, "successes": hit_rate * n, "n": n,
                 "horizon_days": h, "vol_state": vs}
            if clustering:
                c["clustering"] = clustering
            out.append(c)
    return out


class TestV1PathIsUnchanged:
    def test_edge_z_is_untouched_without_the_correction(self):
        """ORDER 27: the declared v1 bars stand for v1. The multiplicity
        correction must not reach back and restate them."""
        for m in (1, 3, 8):
            assert trust_router.edge_z(m, cluster_adjust=False) == \
                trust_router.EDGE_Z

    def test_module_default_is_ON_since_the_attended_flip(self):
        """Flipped 2026-08-23 on Murat's explicit confirmation.

        The G1 correlated-worlds battery measured OFF at a 38.7% null-world
        recommendation rate against ORDER 27's bar, so OFF was measurably
        broken. It was safe to flip only because the setting had become part of
        the POLICY IDENTITY of the books that consume it, making the flip
        self-refusing rather than silent: PROFIT_ALLOCATOR_v1 could not
        continue under its own seed and was retired, history untouched.

        Still an attendance guard — it now pins that nobody flips it BACK
        without the decision being taken.
        """
        assert trust_router.CLUSTER_ADJUST_DEFAULT is True

    def test_cells_without_clustering_are_counted_as_rows(self):
        cells = _cells("a", 0.5, 40)
        assert trust_router._effective_n(cells, cluster_adjust=True) == \
            trust_router._effective_n(cells, cluster_adjust=False)


class TestTheCorrection:
    def test_the_bar_rises_with_the_number_of_actors(self):
        """Best-of-m is a multiple comparison. The bar must know m."""
        z1 = trust_router.edge_z(1, cluster_adjust=True)
        z3 = trust_router.edge_z(3, cluster_adjust=True)
        z8 = trust_router.edge_z(8, cluster_adjust=True)
        assert z1 < z3 < z8
        assert z1 == pytest.approx(1.645, abs=0.01)  # one-sided 5%

    def test_clustered_cells_carry_less_evidence(self):
        clustered = _cells("a", 0.5, 40, clustering={"n_effective": 5,
                                                     "deff": 8.0,
                                                     "n_clusters": 5})
        assert trust_router._effective_n(clustered, cluster_adjust=True) < \
            trust_router._effective_n(clustered, cluster_adjust=False)

    def test_pooled_actor_count_caps_the_summed_cells(self):
        """The three vol_state cells are three views of the same mornings;
        their effective counts must not be added."""
        cells = _cells("a", 0.5, 40, clustering={"n_effective": 12,
                                                 "deff": 3.0, "n_clusters": 12})
        summed = trust_router._hierarchy(cells, "a", {}, cluster_adjust=True)
        capped = trust_router._hierarchy(
            cells, "a", {}, cluster_adjust=True,
            actor_clustering={"a": {"n_effective": 12}})
        assert capped[0][2] == 12
        assert capped[0][2] < summed[0][2]

    def test_a_harmful_actor_is_not_funded_for_being_unproven(self):
        """Under the correction the NO_EDGE fallback funds only actors at or
        above the prior — failing to reject harm is not evidence of safety."""
        cells = (_cells("good", 0.52, 40) + _cells("bad", 0.30, 40))
        out = trust_router.trust_weights(cells, cluster_adjust=True)
        assert out["verdict"] == "NO_EDGE"
        assert out["actors"]["bad"]["weight"] == 0.0
        assert "bad" in out["excluded_below_prior"]

    def test_requested_is_not_the_same_as_applied(self, tmp_path):
        """A ledger whose cells carry no clustering silently falls back to row
        counts. The receipt must say so rather than claim an adjustment it
        could not make."""
        rec = trust_router.recommend(root=tmp_path, cluster_adjust=True)
        assert rec["cluster_adjust"] is True
        assert rec["cluster_adjust_effective"] is False


# ── the gate ────────────────────────────────────────────────────────────────
def _passing_receipt(**over):
    """A receipt that clears every bar, fingerprinted to the LIVE router."""
    fp = G.live_router_fingerprint(trust_router.CLUSTER_ADJUST_DEFAULT)
    rec = {
        "mode": "KNOWN_ANSWER_BATTERY",
        "gate": "ROUTER_CAPITAL_AUTHORITY",
        "router": fp,
        "battery": {"battery_version": "G1_CORRELATED_BATTERY_v2"},
        "n_null_worlds": 300,
        "null_recommendation_rate": 0.03,
        "null_recommendation_rate_ci95": [0.015, 0.058],
        "null_capital_exposure_deployed": 0.03,
        "null_capital_exposure_given_deployed": 1.0,
        "null_capital_exposure_fallback": 0.5,
        "edge_recovery_rate": 0.85,
        "harmful_leak_worlds": 1,
        "arms": {"harmful": {"n_worlds": 80}},
    }
    rec.update(over)
    return rec


def _write(tmp_path, rec):
    p = tmp_path / "battery.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p


class TestGateRefusals:
    def test_a_receipt_that_is_not_a_battery_is_refused(self, tmp_path):
        p = _write(tmp_path, _passing_receipt(mode="LIVE_EVIDENCE"))
        with pytest.raises(G.RouterCapitalRefused, match="KNOWN_ANSWER"):
            G.evaluate_router_license(p)

    def test_a_receipt_for_another_gate_is_refused(self, tmp_path):
        p = _write(tmp_path, _passing_receipt(gate="SOMETHING_ELSE"))
        with pytest.raises(G.RouterCapitalRefused, match="governs"):
            G.evaluate_router_license(p)

    def test_a_receipt_measuring_another_estimator_is_refused(self, tmp_path):
        """The load-bearing refusal: the correction lives in a function body,
        so a fingerprint of constants alone would keep licensing across
        exactly the edits that change the answer."""
        rec = _passing_receipt()
        rec["router"] = {**rec["router"], "estimator_source_sha": "0" * 16}
        with pytest.raises(G.RouterCapitalRefused, match="different router"):
            G.evaluate_router_license(_write(tmp_path, rec))

    def test_a_receipt_measured_under_an_unflipped_setting_is_refused(
            self, tmp_path):
        """Evidence for a router nobody is running licenses nothing. This is
        what keeps the cluster_adjust flip an ATTENDED decision."""
        other = not trust_router.CLUSTER_ADJUST_DEFAULT
        rec = _passing_receipt()
        rec["router"] = G.live_router_fingerprint(other)
        with pytest.raises(G.RouterCapitalRefused, match="attended"):
            G.evaluate_router_license(_write(tmp_path, rec))

    def test_too_few_worlds_is_refused(self, tmp_path):
        p = _write(tmp_path, _passing_receipt(n_null_worlds=20))
        with pytest.raises(G.RouterCapitalRefused, match="rule of three"):
            G.evaluate_router_license(p)

    def test_unreported_capital_exposure_is_refused(self, tmp_path):
        rec = _passing_receipt()
        del rec["null_capital_exposure_fallback"]
        with pytest.raises(G.RouterCapitalRefused, match="capital exposure"):
            G.evaluate_router_license(_write(tmp_path, rec))

    def test_a_missing_recovery_number_is_refused(self, tmp_path):
        rec = _passing_receipt()
        rec["edge_recovery_rate"] = None
        with pytest.raises(G.RouterCapitalRefused, match="never recommends"):
            G.evaluate_router_license(_write(tmp_path, rec))

    def test_a_missing_harmful_arm_is_refused(self, tmp_path):
        rec = _passing_receipt()
        rec["arms"] = {}
        with pytest.raises(G.RouterCapitalRefused, match="harmful-world arm"):
            G.evaluate_router_license(_write(tmp_path, rec))


class TestGateVerdictsAreReachable:
    def test_pass_is_reachable(self, tmp_path):
        out = G.evaluate_router_license(_write(tmp_path, _passing_receipt()))
        assert out["status"] == "PASS"
        assert G.assert_router_licensed(_write(tmp_path, _passing_receipt()))

    def test_a_high_false_positive_rate_fails_rather_than_refuses(self,
                                                                  tmp_path):
        """A battery that RAN and did badly is a finding, not a missing
        input — the two must not arrive as the same exception."""
        p = _write(tmp_path, _passing_receipt(null_recommendation_rate=0.30))
        out = G.evaluate_router_license(p)
        assert out["status"] == "FAIL"
        assert out["checks"]["null_recommendation_rate"]["passed"] is False

    def test_a_router_that_never_recommends_cannot_pass(self, tmp_path):
        """The condition ORDER 27 did not state: a dead instrument has a
        perfect false-positive rate."""
        p = _write(tmp_path, _passing_receipt(null_recommendation_rate=0.0,
                                              edge_recovery_rate=0.0))
        assert G.evaluate_router_license(p)["status"] == "FAIL"

    def test_assert_names_the_number_that_failed(self, tmp_path):
        p = _write(tmp_path, _passing_receipt(null_recommendation_rate=0.30))
        with pytest.raises(G.RouterCapitalRefused, match="0.3"):
            G.assert_router_licensed(p)


class TestTheLivePin:
    """The shipped receipts, read exactly as a caller would read them.

    These pin the CURRENT state of the programme, not a hypothetical. Since
    the 2026-08-23 flip that state is:

      * the v1 receipt describes a router nobody runs -> refused on fingerprint;
      * the v1.1 receipt clears ORDER 27's false-positive bar (0.03 <= 0.05);
      * capital is STILL unlicensed, because the router cannot RECOVER a real
        edge at the arena's current breadth. That is a POWER problem, and only
        decision days buy it.

    If the last one turns green without those days accruing, the gate has
    inverted and every refusal above is decoration.
    """

    def test_the_v1_receipt_no_longer_describes_the_running_router(self):
        """Since the flip, the v1 receipt measures a setting nobody runs.

        Refused on FINGERPRINT, not on its numbers: a battery passed under a
        configuration that is switched off is a description of a different
        router.
        """
        assert G.DEFAULT_RECEIPT.exists(), (
            "the governing battery receipt is missing — the gate would refuse "
            "every caller, which is safe but tells nobody why")
        with pytest.raises(G.RouterCapitalRefused, match="cluster_adjust"):
            G.evaluate_router_license()

    def test_the_flip_bought_the_false_positive_fix(self):
        """What the flip actually purchased, and the only thing it purchased."""
        p = G.DEFAULT_RECEIPT.parent / \
            "g1_correlated_battery_v1_1_cluster_adjust.json"
        assert p.exists()
        rec = json.loads(p.read_text(encoding="utf-8"))
        assert rec["null_recommendation_rate"] <= 0.05, (
            "the corrected router no longer clears ORDER 27's bar — that bar "
            "is the whole reason the flip was taken")

    def test_capital_is_STILL_unlicensed_and_the_reason_is_POWER(self):
        """The flip must not be read as licensing capital. It does not.

        Clearing the false-positive bar is necessary and not sufficient. The
        router still fails `edge_recovery_rate`: it cannot RECOVER a real edge
        at the arena's current breadth (~0.19 against a 0.7 bar). Only DECISION
        DAYS buy that — roughly six months of live arena — and no amount of
        configuration substitutes for them.

        If this turns green without those days accruing, the gate has inverted
        and every refusal above is decoration.
        """
        p = G.DEFAULT_RECEIPT.parent / \
            "g1_correlated_battery_v1_1_cluster_adjust.json"
        out = G.evaluate_router_license(p)
        assert out["status"] == "FAIL"
        assert out["checks"]["edge_recovery_rate"]["value"] < 0.7
        with pytest.raises(G.RouterCapitalRefused, match="edge_recovery_rate"):
            G.assert_router_licensed(p)
