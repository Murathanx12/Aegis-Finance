"""The registry must make a research verdict enforceable, not decorative.

Each test pins one way a killed mechanism could quietly reach the portfolio
manager: a role the grade forbids, a weight above 1, an unregistered signal
treated as neutral, a "new" mechanism that names no corpse, an uncalibrated
weight read as perfect.
"""
from __future__ import annotations

import pytest
import yaml

from backend.services import signal_registry as SR


@pytest.fixture
def reg():
    return SR.load()


def _write(tmp_path, signals, **extra):
    p = tmp_path / "reg.yaml"
    p.write_text(yaml.safe_dump({"schema": "signal-registry-v1",
                                 "written": "2026-01-01",
                                 "signals": signals, **extra}), encoding="utf-8")
    SR.load.cache_clear()
    return str(p)


# ───────────────────────── the shipped registry ─────────────────────────────

def test_the_shipped_registry_loads_and_validates(reg):
    assert reg.schema == "signal-registry-v1"
    assert len(reg.signals) >= 25


def test_the_corpses_are_closed_and_cannot_pick(reg):
    """These specific mechanisms have receipts. None may choose a stock."""
    for sid in ("analyst_target_upside_xs", "momentum_12_1",
                "inst_ownership_level_13f", "trailing_stop_rule",
                "options_ranking_raw", "reversal_dip", "accruals",
                "llm_stock_selection"):
        s = reg.get(sid)
        assert s.is_closed, f"{sid} must be closed"
        assert not reg.permits(sid, "PICKER")
        assert not reg.permits(sid, "FILTER")
        with pytest.raises(SR.ClosedSignalError):
            reg.check_closed(sid)


def test_the_error_tells_you_what_to_do_instead(reg):
    with pytest.raises(SR.ClosedSignalError) as e:
        reg.check_closed("inst_ownership_level_13f")
    msg = str(e.value)
    assert "distinct_from" in msg, "must point at the legitimate route"
    assert "increment over it" in msg, "must demand the corpse as a control arm"


def test_a_new_mechanism_must_name_the_corpse_it_is_not(reg):
    """The 13F successor is the case Murat asked about by name."""
    s = reg.get("specialist_filer_initiation")
    assert "inst_ownership_level_13f" in s.distinct_from
    assert reg.get("inst_ownership_level_13f").is_closed
    assert not s.allowed_in_pm, "a hypothesis is queued, not live"
    assert s.queued and not s.is_closed, "queued is not the same as killed"


def test_closed_and_queued_are_different_things(reg):
    """Collapsing them makes every unrun idea look like a corpse."""
    closed = {s.signal_id for s in reg.closed()}
    queued = {s.signal_id for s in reg.queued()}
    assert not (closed & queued)
    assert "analyst_target_revision" in queued
    assert "analyst_target_upside_xs" in closed


def test_the_analyst_split_is_encoded(reg):
    """Levels are closed; the haircut target survives ONLY as a risk input."""
    assert reg.get("analyst_target_upside_xs").is_closed
    assert reg.permits("analyst_target_level_haircut", "RISK_INPUT")
    assert not reg.permits("analyst_target_level_haircut", "PICKER"), (
        "sizing a chosen name is not the same as choosing one")


def test_uncalibrated_resolves_to_unknown_never_to_perfect(reg):
    unc = reg.uncalibrated()
    assert unc, "several live signals are uncalibrated and must say so"
    for s in unc:
        assert s.reliability_weight is None
        assert s.weight == SR.UNCALIBRATED == 0.5
        assert "UNCALIBRATED" in s.label()


def test_no_weight_can_amplify(reg):
    for s in reg.signals.values():
        assert 0.0 <= s.weight <= 1.0


def test_every_graded_verdict_carries_a_receipt(reg):
    for s in reg.signals.values():
        if s.evidence_grade in {"VALIDATED", "SUPPORTED", "REJECTED", "PERVERSE"}:
            assert s.receipts, f"{s.signal_id}: a verdict without a receipt"


def test_an_unregistered_signal_raises_rather_than_scoring_zero(reg):
    with pytest.raises(SR.RegistryError) as e:
        reg.get("follow_the_smart_money")
    assert "registered before it can be used" in str(e.value)


# ───────────────────────── malformed registries ─────────────────────────────

def test_a_killed_mechanism_given_a_picker_role_is_rejected(tmp_path):
    path = _write(tmp_path, [{
        "signal_id": "zombie", "evidence_grade": "REJECTED",
        "permitted_role": "PICKER", "allowed_in_pm": True,
        "receipts": ["somewhere"]}])
    with pytest.raises(SR.RegistryError) as e:
        SR.load(path)
    assert "may not pick" in str(e.value)
    SR.load.cache_clear()


def test_a_weight_above_one_is_rejected(tmp_path):
    path = _write(tmp_path, [{
        "signal_id": "greedy", "evidence_grade": "OBSERVATIONAL",
        "permitted_role": "FILTER", "allowed_in_pm": True,
        "reliability_weight": 1.4}])
    with pytest.raises(SR.RegistryError) as e:
        SR.load(path)
    assert "discounts, it never amplifies" in str(e.value)
    SR.load.cache_clear()


def test_a_typo_in_a_field_name_is_rejected(tmp_path):
    """A silently-dropped field is a silently-dropped verdict."""
    path = _write(tmp_path, [{
        "signal_id": "typo", "evidence_grade": "OBSERVATIONAL",
        "permitted_role": "FILTER", "allowed_in_pm": True,
        "permited_role": "PICKER"}])
    with pytest.raises(SR.RegistryError) as e:
        SR.load(path)
    assert "unknown field" in str(e.value)
    SR.load.cache_clear()


def test_distinct_from_must_point_at_a_real_closed_signal(tmp_path):
    path = _write(tmp_path, [{
        "signal_id": "successor", "evidence_grade": "HYPOTHESIS",
        "permitted_role": "PICKER", "allowed_in_pm": False,
        "distinct_from": ["a_corpse_that_does_not_exist"]}])
    with pytest.raises(SR.RegistryError) as e:
        SR.load(path)
    assert "must exist for the claim to mean anything" in str(e.value)
    SR.load.cache_clear()


def test_a_hypothesis_may_not_be_filed_as_closed(tmp_path):
    path = _write(tmp_path, [{
        "signal_id": "confused", "evidence_grade": "HYPOTHESIS",
        "permitted_role": "CLOSED", "allowed_in_pm": False}])
    with pytest.raises(SR.RegistryError) as e:
        SR.load(path)
    assert "queued, not killed" in str(e.value)
    SR.load.cache_clear()


def test_a_missing_registry_raises_rather_than_permitting_everything(tmp_path):
    SR.load.cache_clear()
    with pytest.raises(SR.RegistryError):
        SR.load(str(tmp_path / "absent.yaml"))
    SR.load.cache_clear()


def test_evidence_lines_flag_an_unregistered_signal(reg):
    lines = SR.evidence_lines(["profitability_small", "not_a_real_signal"])
    assert any("NOT REGISTERED" in ln for ln in lines)


# ────────────── an unreadable registry must not read as "all clear" ──────────

def test_a_missing_registry_makes_the_brief_shout_not_go_quiet(monkeypatch):
    """The house bug, in the one function whose job is to notice a problem."""
    from backend.services import pm_actions as A

    def boom(*a, **k):
        raise SR.RegistryError("registry file deleted")

    monkeypatch.setattr(SR, "load", boom)
    conflicts = A._registry_conflicts(
        [{"action": "BUY", "ticker": "AAA", "held": False}])
    assert conflicts, "no warning would read identically to no conflict"
    assert conflicts[0]["severity"] == "HIGH"
    assert "NOTHING in this brief was checked" in conflicts[0]["what"]
    assert "not evidence of absence" in conflicts[0]["consequence"]


def test_a_buy_ranked_on_a_perverse_signal_is_flagged():
    from backend.services import pm_actions as A
    SR.load.cache_clear()
    conflicts = A._registry_conflicts([
        {"action": "BUY", "ticker": "NVDA", "held": False},
        {"action": "HOLD", "ticker": "SOC", "held": True}])
    assert conflicts and conflicts[0]["signal"] == "analyst_target_upside_xs"
    assert conflicts[0]["grade"] == "PERVERSE"
    assert conflicts[0]["affects"] == ["NVDA"], "held names are not the issue"


def test_no_buys_means_no_conflict():
    from backend.services import pm_actions as A
    SR.load.cache_clear()
    assert A._registry_conflicts(
        [{"action": "HOLD", "ticker": "SOC", "held": True}]) == []
