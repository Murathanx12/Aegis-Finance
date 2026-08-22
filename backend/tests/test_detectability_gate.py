"""The planted-world detectability gate: refusals, verdicts, and the live pin.

The gate exists because TOURNAMENT-1's sensitivity receipts were written and
NOTHING read them — a TOURNAMENT-2 could have been registered over a
demonstrably blind instrument. These tests exercise every refusal with the
input actually missing, both verdicts with synthetic receipts, and pin the
one fact the shipped receipts prove: at panel-1 the gate FAILS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.detectability_gate import (DetectabilityRefused,
                                                 REQUIRED_WORLDS,
                                                 assert_detectable,
                                                 evaluate_detectability)

PANEL_HASH = "cafe0123deadbeef"
LIVE_RECEIPTS = (Path(__file__).resolve().parents[1]
                 / "data" / "optimus" / "aegis_panel")


def _receipt(world: str, *, panel_hash: str = PANEL_HASH,
             target_ic: float = 0.03, mean: float = 0.02,
             ci_lo: float = 0.005, mode: str = "SENSITIVITY_WORLD") -> dict:
    return {
        "trial": "TEST-WORLD", "mode": mode, "world": world,
        "panel_hash": panel_hash, "planted": {"target_ic": target_ic},
        "contrasts": {"full_lgbm_minus_floor":
                      {"contrast": {"mean": mean, "ci_lo": ci_lo},
                       "verdict": "irrelevant-to-the-gate"}},
    }


def _write_worlds(tmp_path: Path, **overrides) -> Path:
    for world in REQUIRED_WORLDS:
        payload = overrides.get(world, _receipt(world))
        (tmp_path / f"tournament_planted_{world}.json").write_text(
            json.dumps(payload), encoding="utf-8")
    return tmp_path


def _evaluate(receipt_dir, **kw):
    kw.setdefault("panel_hash", PANEL_HASH)
    kw.setdefault("declared_ic", 0.03)
    kw.setdefault("min_recovery", 0.5)
    return evaluate_detectability(receipt_dir, **kw)


class TestRefusals:
    def test_missing_directory_refuses(self, tmp_path):
        with pytest.raises(DetectabilityRefused, match="does not exist"):
            _evaluate(tmp_path / "never_made")

    def test_missing_world_receipt_refuses(self, tmp_path):
        _write_worlds(tmp_path)
        (tmp_path / "tournament_planted_linear_hetero.json").unlink()
        with pytest.raises(DetectabilityRefused, match="linear_hetero"):
            _evaluate(tmp_path)

    def test_panel_hash_mismatch_refuses(self, tmp_path):
        """The receipt that must NOT license panel-2: one minted on panel-1."""
        _write_worlds(tmp_path)
        with pytest.raises(DetectabilityRefused, match="another panel"):
            _evaluate(tmp_path, panel_hash="a_different_panel")

    def test_planted_larger_than_declared_refuses(self, tmp_path):
        """Recovering a 0.05 world says nothing about a 0.03 claim."""
        _write_worlds(tmp_path, linear=_receipt("linear", target_ic=0.05,
                                                mean=0.04, ci_lo=0.02))
        with pytest.raises(DetectabilityRefused, match="exceeds the declared"):
            _evaluate(tmp_path)

    def test_empty_required_worlds_refuses(self, tmp_path):
        _write_worlds(tmp_path)
        with pytest.raises(DetectabilityRefused, match="vacuously"):
            _evaluate(tmp_path, required_worlds=())

    def test_undeclared_bars_refuse(self, tmp_path):
        _write_worlds(tmp_path)
        with pytest.raises(DetectabilityRefused, match="declared_ic"):
            _evaluate(tmp_path, declared_ic=0.0)
        with pytest.raises(DetectabilityRefused, match="min_recovery"):
            _evaluate(tmp_path, min_recovery=0.0)

    def test_wrong_mode_stamp_refuses(self, tmp_path):
        _write_worlds(tmp_path, linear=_receipt("linear", mode="PRIMARY"))
        with pytest.raises(DetectabilityRefused, match="SENSITIVITY_WORLD"):
            _evaluate(tmp_path)

    def test_arm_without_ci_refuses(self, tmp_path):
        broken = _receipt("linear")
        del broken["contrasts"]["full_lgbm_minus_floor"]["contrast"]["ci_lo"]
        _write_worlds(tmp_path, linear=broken)
        with pytest.raises(DetectabilityRefused, match="mean/ci_lo"):
            _evaluate(tmp_path)


class TestVerdicts:
    def test_all_worlds_recovering_is_pass(self, tmp_path):
        result = _evaluate(_write_worlds(tmp_path))
        assert result["status"] == "PASS"
        assert all(w["passed"] for w in result["worlds"])
        # assert_detectable returns the same evaluation rather than raising
        assert assert_detectable(tmp_path, panel_hash=PANEL_HASH,
                                 declared_ic=0.03,
                                 min_recovery=0.5)["status"] == "PASS"

    def test_one_blind_world_is_fail_and_named(self, tmp_path):
        _write_worlds(tmp_path, linear_hetero=_receipt(
            "linear_hetero", mean=0.002, ci_lo=-0.003))
        result = _evaluate(tmp_path)
        assert result["status"] == "FAIL"
        with pytest.raises(DetectabilityRefused, match="linear_hetero"):
            assert_detectable(tmp_path, panel_hash=PANEL_HASH,
                              declared_ic=0.03, min_recovery=0.5)

    def test_ci_including_zero_fails_even_with_a_big_mean(self, tmp_path):
        """A point recovery the bootstrap cannot distinguish from zero is
        not a demonstration — it is the shape TOURNAMENT-1 measured."""
        _write_worlds(tmp_path, linear=_receipt("linear", mean=0.02,
                                                ci_lo=-0.001))
        assert _evaluate(tmp_path)["status"] == "FAIL"

    def test_mean_below_recovery_bar_fails(self, tmp_path):
        _write_worlds(tmp_path, linear=_receipt("linear", mean=0.01,
                                                ci_lo=0.002))
        result = _evaluate(tmp_path)  # 0.01 < 0.5 * 0.03
        assert result["status"] == "FAIL"
        blind = [w for w in result["worlds"] if not w["passed"]]
        assert [w["world"] for w in blind] == ["linear"]


class TestLivePanel1Receipts:
    """Pin the true current state: the shipped panel-1 receipts FAIL the gate.

    This is the fact the whole module enforces — if a refactor ever makes
    these receipts read as PASS, the gate has silently inverted and this
    test is the alarm. Visible skip when the tracked receipts are absent
    (CI checkouts without the data directory)."""

    def test_panel1_is_blind_at_its_own_hash(self):
        first = LIVE_RECEIPTS / "tournament_planted_linear.json"
        if not first.exists():
            pytest.skip("panel-1 planted receipts not present in this checkout")
        panel_hash = json.loads(first.read_text(encoding="utf-8"))["panel_hash"]
        result = evaluate_detectability(LIVE_RECEIPTS, panel_hash=panel_hash,
                                        declared_ic=0.03, min_recovery=0.5)
        assert result["status"] == "FAIL"
        assert all(not w["passed"] for w in result["worlds"]), (
            "a shipped panel-1 world now reads as RECOVERED — either the "
            "receipts changed or the gate inverted; both demand a look")
