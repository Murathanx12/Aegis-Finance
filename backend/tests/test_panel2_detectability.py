"""The panel-2 detectability receipts, read exactly as TOURNAMENT-2 will read them.

`scripts/panel2_planted_worlds.py` produces these; `detectability_gate` consumes
them; this pins the seam. It is deliberately CI-COMPLETE: every assertion reads
the committed JSON receipts and takes the panel hash FROM the receipt rather
than recomputing it, because the 4.18 GB panel is gitignored and a test that
silently skipped in CI would leave the gate's most important wiring unchecked
exactly where nobody looks.

What must hold, and why each one is here:

  * the three worlds the gate REQUIRES by name all exist. A gate whose
    required-worlds list outruns the receipts on disk refuses every caller,
    which is safe and useless;
  * every receipt is stamped SENSITIVITY_WORLD and carries ONE panel hash.
    Two hashes across three worlds would mean the panel changed mid-run and
    the receipts describe two instruments;
  * panel-1's receipts still license nothing here. That refusal is the whole
    reason the gate takes a hash at all;
  * a prereg claiming to bound an effect SMALLER than the one planted is
    refused. Recovering 0.03 says nothing about 0.01, and this is the
    direction a future prereg would be tempted to drift.
"""

from __future__ import annotations

import json

import pytest

from backend.services import detectability_gate as G
from backend.services.aegis_panel2_spec import OUT_DIR

RECEIPT_DIR = OUT_DIR / "panel2_detectability"
PANEL1_DIR = OUT_DIR
PLANTED_IC = 0.03

#: The arms panel-2 runs. Ridge and MLP do not fit at this scale on this
#: machine; the z-label pair does, and had to be run because panel-1 ran it —
#: a narrower arm set silently compared against a wider one would credit the
#: difference to the panel.
ALL_PANEL2_ARMS = ("floor_lgbm", "full_lgbm",
                   "floor_lgbm_zlabel", "full_lgbm_zlabel")


def _receipt(world: str) -> dict:
    p = RECEIPT_DIR / G.RECEIPT_TEMPLATE.format(world=world)
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def receipts():
    missing = [w for w in G.REQUIRED_WORLDS
               if not (RECEIPT_DIR / G.RECEIPT_TEMPLATE.format(world=w)).exists()]
    if missing:
        pytest.fail(
            f"panel-2 detectability receipts missing for {missing}. These are "
            f"committed artifacts, not build output — the gate refuses every "
            f"caller without them, and TOURNAMENT-2 cannot be registered.")
    return {w: _receipt(w) for w in G.REQUIRED_WORLDS}


class TestTheReceipts:
    def test_all_required_worlds_are_present(self, receipts):
        assert set(receipts) == set(G.REQUIRED_WORLDS)

    def test_every_receipt_is_a_sensitivity_world(self, receipts):
        """Never market evidence, and the stamp is what enforces it."""
        for w, r in receipts.items():
            assert r["mode"] == "SENSITIVITY_WORLD", w
            assert r["panel"] == "AEGIS-PANEL-2", w

    def test_one_panel_and_one_instrument_across_all_three(self, receipts):
        hashes = {r["panel_hash"] for r in receipts.values()}
        specs = {r["spec_hash"] for r in receipts.values()}
        assert len(hashes) == 1, f"receipts span {len(hashes)} panels: {hashes}"
        assert len(specs) == 1, f"receipts span {len(specs)} instruments"

    def test_the_planted_size_is_the_declared_one(self, receipts):
        for w, r in receipts.items():
            assert r["planted"]["target_ic"] == PLANTED_IC, w

    def test_each_receipt_names_what_it_did_not_run(self, receipts):
        """Omitted arms are part of the claim's scope. A receipt that hid them
        would read as 'the instrument' when it was two arms of it."""
        for w, r in receipts.items():
            assert r["arms_omitted"], w
            assert r["arms_omitted_reason"], w


class TestTheGateReadsThem:
    def test_the_gate_evaluates_without_refusing(self, receipts):
        """Inputs present and consistent — so the gate reaches a VERDICT
        rather than a refusal. Whether that verdict is PASS depends on the bar
        the prereg declares, which is the next session's decision."""
        phash = next(iter(receipts.values()))["panel_hash"]
        out = G.evaluate_detectability(RECEIPT_DIR, panel_hash=phash,
                                       declared_ic=PLANTED_IC,
                                       min_recovery=0.25)
        assert out["status"] in ("PASS", "FAIL")
        assert {w["world"] for w in out["worlds"]} == set(G.REQUIRED_WORLDS)
        for w in out["worlds"]:
            assert w["target_ic"] == PLANTED_IC
            assert w["best_arm"].startswith("full_")

    def test_panel1_receipts_still_license_nothing_here(self, receipts):
        """The cross-panel refusal, on the real hashes. If this ever passes,
        18x more data is being certified by evidence from the panel that was
        blind."""
        phash = next(iter(receipts.values()))["panel_hash"]
        with pytest.raises(G.DetectabilityRefused, match="another panel"):
            G.evaluate_detectability(PANEL1_DIR, panel_hash=phash,
                                     declared_ic=PLANTED_IC,
                                     min_recovery=0.25)

    def test_a_smaller_declared_effect_is_refused(self, receipts):
        """Recovering a 0.03 world says nothing about a 0.01 one, and 0.01 is
        the economic bar — precisely the number a later prereg would be
        tempted to quote while citing these receipts."""
        phash = next(iter(receipts.values()))["panel_hash"]
        with pytest.raises(G.DetectabilityRefused, match="exceeds the declared"):
            G.evaluate_detectability(RECEIPT_DIR, panel_hash=phash,
                                     declared_ic=0.01, min_recovery=0.25)

    def test_a_wrong_panel_hash_is_refused(self, receipts):
        with pytest.raises(G.DetectabilityRefused, match="another panel"):
            G.evaluate_detectability(RECEIPT_DIR, panel_hash="deadbeefdeadbeef",
                                     declared_ic=PLANTED_IC, min_recovery=0.25)


class TestScaleMovedTheInstrument:
    """The finding, pinned so a later panel change cannot erase it silently."""

    ARM = "full_lgbm_minus_floor"

    @staticmethod
    def _best_full(rec):
        arms = {k: v for k, v in rec["contrasts"].items()
                if k.startswith("full_")}
        return max((v["contrast"]["mean"], k) for k, v in arms.items())

    def test_every_panel2_world_now_excludes_zero(self):
        """THE headline, and the one claim that holds in all three worlds.

        On panel-1 every planted world's best arm had an interval containing
        zero — the instrument could not distinguish a planted 0.03 from
        nothing. On panel-2 every world's best arm excludes zero. That is what
        changed; the SIZE of what it recovers is a separate question the next
        test refuses to overstate.
        """
        for world in G.REQUIRED_WORLDS:
            rec = _receipt(world)
            _, best = self._best_full(rec)
            ci_lo = rec["contrasts"][best]["contrast"]["ci_lo"]
            assert ci_lo > 0, f"{world}: best arm {best} ci_lo {ci_lo:+.5f}"

    @pytest.mark.parametrize("world", ["linear", "linear_dense"])
    def test_the_shared_arm_recovers_more_at_scale(self, world):
        """Compared on `full_lgbm`, the arm both panels ran.

        `linear_hetero` is deliberately EXCLUDED from this comparison and is
        not an oversight: that world scales its label by the panel's own
        realised per-month dispersion, so panel-2's version contains the 1930s
        and is a HARDER world, not the same world with more rows. Its raw arm
        recovers less than panel-1's (+0.00145 vs +0.00205) and that is not
        evidence that scale hurt — the two numbers describe different worlds.
        """
        p1 = json.loads((PANEL1_DIR / G.RECEIPT_TEMPLATE.format(world=world))
                        .read_text(encoding="utf-8"))
        a1 = p1["contrasts"][self.ARM]["contrast"]["mean"]
        a2 = _receipt(world)["contrasts"][self.ARM]["contrast"]["mean"]
        assert a2 > a1, (
            f"{world}: panel-2's full_lgbm recovered {a2:+.5f} vs panel-1's "
            f"{a1:+.5f} — the scale-up did not improve detectability for the "
            f"arm both panels ran")

    def test_zlabel_collapses_the_hetero_world_onto_the_dense_one(self):
        """An identity, asserted so nobody later 'fixes' the duplication.

        The hetero label is sd_month * (0.03*zc + noise); per-date z-scoring
        divides by that same within-month sd, so the z-labelled training
        target is EXACTLY the dense world's, and per-date Spearman is
        invariant to the positive within-date scalar. Hence identical numbers.
        The consequence is the finding: all of the hetero world's extra
        difficulty lives in the TRAINING OBJECTIVE, and z-labelling removes it.
        """
        dense = _receipt("linear_dense")["contrasts"]
        hetero = _receipt("linear_hetero")["contrasts"]
        z = "full_lgbm_zlabel_minus_floor"
        assert dense[z]["contrast"]["mean"] == hetero[z]["contrast"]["mean"]
        # ...while the RAW arms genuinely differ, which is what makes the
        # identity meaningful rather than a sign the two runs were the same.
        raw = self.ARM
        assert dense[raw]["contrast"]["mean"] != hetero[raw]["contrast"]["mean"]

    def test_the_objective_not_the_data_rescues_the_realistic_world(self):
        """panel-1 asked this and could not answer it: 'if pooled raw-MSE is
        the binding constraint, the zlabel arms recover materially more.' At
        panel-1's scale they measured +0.00008 — nothing. Here they more than
        double the hetero world's recovery and move its interval off zero."""
        h = _receipt("linear_hetero")["contrasts"]
        raw = h[self.ARM]["contrast"]
        zl = h["full_lgbm_zlabel_minus_floor"]["contrast"]
        assert zl["mean"] > 2 * raw["mean"]
        assert raw["ci_lo"] <= 0 < zl["ci_lo"]

    def test_panel2s_best_arm_is_a_conservative_floor_on_the_instrument(self):
        """panel-2 runs a strict SUBSET of panel-1's arms, so its
        best-of-arms — which is what the gate reads — can only understate what
        the full instrument would recover. Stated as a test so the omission
        stays a known limit rather than an unnoticed one.

        `full_ridge` is the specific loss: it was panel-1's BEST arm in both
        dense worlds, and a dense linear carrier is exactly what a linear model
        should find and a tree should struggle with. Any future reading of a
        weak dense recovery here has to account for that before blaming scale.
        """
        for world in G.REQUIRED_WORLDS:
            p2 = _receipt(world)
            assert set(p2["arms_run"]) <= set(ALL_PANEL2_ARMS), world
            assert "full_ridge" in p2["arms_omitted"], world

        # panel-1 ran ridge in the two DENSE worlds only — it is the arm that
        # won both of them, which is exactly why losing it here matters and
        # why the loss is confined to those two.
        for world in ("linear_dense", "linear_hetero"):
            p1 = json.loads((PANEL1_DIR / G.RECEIPT_TEMPLATE.format(world=world))
                            .read_text(encoding="utf-8"))
            arms = {k.replace("_minus_floor", ""): v["contrast"]["mean"]
                    for k, v in p1["contrasts"].items()}
            assert "full_ridge" in arms, world
            assert arms["full_ridge"] == max(
                v for k, v in arms.items() if k.startswith("full_")), (
                f"{world}: ridge was NOT panel-1's best arm — the reason this "
                f"omission is worth flagging does not hold")

    def test_panel1_was_blind_in_every_required_world(self):
        """The baseline the panel-2 claim is measured against: on panel-1 every
        world's interval crossed zero."""
        for world in G.REQUIRED_WORLDS:
            rec = json.loads(
                (PANEL1_DIR / G.RECEIPT_TEMPLATE.format(world=world))
                .read_text(encoding="utf-8"))
            arms = {k: v for k, v in rec["contrasts"].items()
                    if k.startswith("full_")}
            assert all(v["contrast"]["ci_lo"] <= 0 for v in arms.values()), \
                f"{world}: a panel-1 arm excluded zero after all"
