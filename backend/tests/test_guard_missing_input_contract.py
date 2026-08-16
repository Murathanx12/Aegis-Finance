"""Hand every guard nothing, and demand a refusal.

The shared contract from Order 8. The list is not maintained by memory: any
module under `services/` that defines its own refusal exception must appear
here, and `test_every_guard_is_enrolled` fails until it does.
"""

from __future__ import annotations

import pytest

from backend.tests.guard_contract import (NOT_INPUT_GUARDS,
                                          assert_refuses_missing_input,
                                          discover_guard_modules)


# ── one case per guard: the input that is NOT THERE ────────────────────────
def _case_execution_boundary():
    from backend.services.execution_boundary import (NotReportable,
                                                     gap_is_lost)
    return (lambda: gap_is_lost(""), NotReportable,
            "arrival never declared")


def _case_multiplicity():
    from backend.services.research_gym.multiplicity import (
        MultiplicityRefusal, calendar_of)
    return (lambda: calendar_of("no-pipes-here"), MultiplicityRefusal,
            "window id with no derivable calendar")


def _case_autopsy():
    from backend.services.research_gym.autopsy import (PrecursorRefused,
                                                       compile_precursor)
    return (lambda: compile_precursor({}), PrecursorRefused,
            "precursor spec with no clauses")


def _case_g4_expectation():
    from backend.services.g4_expectation import (ExpectationRecord,
                                                 ExpectationRefused)
    rec = ExpectationRecord(entity="X", entity_id_kind="permno", entity_id="1",
                            event_type="eps", event_id="e1",
                            first_public_ts=None, expectation_asof=None,
                            observed_at=None, tradable_at=None)
    from backend.services.g4_expectation import validate
    return (lambda: validate(rec, strict=True), ExpectationRefused,
            "expectation record with none of its four clocks")


def _case_strategy_library():
    from backend.services.strategy_library import (ClaimIsNotEvidence, SEED)
    return (lambda: SEED[0].measured("post_publication"), ClaimIsNotEvidence,
            "a claim standing in for a measurement")


def _case_matched_controls():
    from backend.services.teacher_library.matched_controls import (
        Candidate, ControlRefused, run_control_family)
    ev = [Candidate(key="a", ticker="A", date="2020-01-02",
                    covariates={"size": 1.0})]
    return (lambda: run_control_family(ev, []), ControlRefused,
            "control family with an empty pool")


def _case_scope():
    from backend.services.research_gym.scope import ScopeRefused, ScopedVerdict
    return (lambda: ScopedVerdict(verdict="REFUTED_IN_SCOPE", scope="",
                                  reason="r"), ScopeRefused,
            "a closing verdict with no scope to close")


def _case_lineage():
    from backend.services.research_gym.lineage import (LabelWindow,
                                                       LeakageRefusal,
                                                       assert_clean)
    idx = [f"2020-01-{d:02d}" for d in range(1, 29)]
    # A 20-row label window whose horizon reaches past the cutoff, with no
    # embargo declared: the leak the module exists to refuse.
    return (lambda: assert_clean(idx, split_cutoff="2020-01-20",
                                 windows=[LabelWindow(name="h20",
                                                      horizon_rows=20)]),
            LeakageRefusal, "labels whose horizon crosses the split cutoff")


def _case_slice_register():
    from backend.services.research_gym.slice_register import (SliceIdentity,
                                                              SliceRefusal)
    from backend.services.research_gym.slice_register import SliceRegister
    ident = SliceIdentity(securities=("AAPL",), start="2020-01-01",
                          end="2020-12-31", outcome_horizon_days=20,
                          outcome_definition="ret")
    reg = SliceRegister(path=tmp_ledger())
    # A CONFIRM with `parents` left silent. `()` is a declaration that nothing
    # selected the rule; None is no declaration at all, and reading silence as
    # `()` is what R13e cost us.
    return (lambda: reg.claim(ident, "CONFIRM", trial="t",
                              consumed_at="2021-01-04",
                              parent_hypotheses=None),
            SliceRefusal, "a confirmation that declares no parent trial")


def _case_evidence_population():
    from backend.services.evidence_population import (PopulationPoolingRefused,
                                                      refuse_pooling)
    return (lambda: refuse_pooling("campaign_forward", "live_forward"),
            PopulationPoolingRefused, "two populations pooled")


def _case_charter():
    from backend.services.research_gym.charter import (ExportRefused,
                                                       TransferTest,
                                                       assert_exportable)
    return (lambda: assert_exportable(
        "m", TransferTest(mechanism="m", origin_episode_ids=[])),
        ExportRefused, "export with no transfer evidence behind it")


def _case_portfolio_factory():
    from backend.services.portfolio_factory import ArchetypeRefused, build
    from backend.services import portfolio_factory as pf
    arch = pf.ARCHETYPES[0] if getattr(pf, "ARCHETYPES", None) else None
    if arch is None:                                    # pragma: no cover
        pytest.skip("no archetype available")
    return (lambda: build([], arch), ArchetypeRefused,
            "portfolio built from no candidates")


def _case_store(tmp_path=None):
    from types import SimpleNamespace
    from backend.services.copy_lab.store import ConfigDrift, assert_config_current
    spec = SimpleNamespace(lane_id="lane-that-was-never-seeded",
                           config_hash="0" * 64)
    return (lambda: assert_config_current(spec), ConfigDrift,
            "config check on a lane that was never seeded")


def _case_winner_loser_factory():
    from backend.services.winner_loser_factory import (Episode,
                                                       LookAheadInMatching,
                                                       assert_pit_strict)
    ep = Episode(entity_id="A", decision_ts="2020-03-02T14:30:00Z",
                 characteristics={"size": 1.0}, characteristics_asof={},
                 outcome=0.1, outcome_horizon_days=20)
    return (lambda: assert_pit_strict(ep), LookAheadInMatching,
            "a covariate with a value and no as-of date")


def _case_null_invariance():
    from backend.services.research_gym.null_invariance import (
        NullContractViolation, NullSpec, verify)
    spec = NullSpec(name="n", preserves=("clustering",))
    return (lambda: verify(spec, {"clustering": 1.0}, []),
            NullContractViolation, "a null verified against no placebos")


def _case_utility():
    from backend.services.research_gym.utility import (ObjectiveMisuse,
                                                       get_objective, score_one)
    obj = get_objective("expected_log_growth")
    if obj.kind != "distribution":                       # pragma: no cover
        pytest.skip("no distribution-kind objective registered")
    return (lambda: score_one(obj, None), ObjectiveMisuse,
            "a distribution objective scored on one episode")


def tmp_ledger():
    import tempfile, pathlib
    return pathlib.Path(tempfile.mkdtemp()) / "slices.jsonl"


def _case_ex_post():
    from backend.services.research_gym.evaluation_only.ex_post import (
        ExPostScale, ExPostUsageError)
    return (lambda: float(ExPostScale(value=1.0, basis="hindsight vol")),
            ExPostUsageError, "a hindsight scale coerced into a live number")


def _case_risk_layer():
    from backend.services.risk_layer import RiskLayerRefused, realised_vol
    # Twelve days is a number. Sizing a real book from it is the honour-system
    # failure with money attached.
    return (lambda: realised_vol([0.01] * 12), RiskLayerRefused,
            "an exposure asked for from too few observations")


def _case_regret():
    from backend.services.research_gym import regret as rg
    pytest.importorskip("backend.services.research_gym.regret")
    return (lambda: rg.menu_hash(None), Exception,
            "a menu hash over nothing")


def _case_iif1_features():
    from backend.services.iif1_features import (PointInTimeViolation,
                                                assert_snapshot_pit_safe)
    return (lambda: assert_snapshot_pit_safe({}), PointInTimeViolation,
            "a snapshot with no information cutoff")


CASES = {
    "execution_boundary": _case_execution_boundary,
    "multiplicity": _case_multiplicity,
    "autopsy": _case_autopsy,
    "g4_expectation": _case_g4_expectation,
    "strategy_library": _case_strategy_library,
    "matched_controls": _case_matched_controls,
    "scope": _case_scope,
    "lineage": _case_lineage,
    "slice_register": _case_slice_register,
    "evidence_population": _case_evidence_population,
    "charter": _case_charter,
    "portfolio_factory": _case_portfolio_factory,
    "store": _case_store,
    "winner_loser_factory": _case_winner_loser_factory,
    "null_invariance": _case_null_invariance,
    "utility": _case_utility,
    "regret": _case_regret,
    "iif1_features": _case_iif1_features,
    "ex_post": _case_ex_post,
    "risk_layer": _case_risk_layer,
}


@pytest.mark.parametrize("module", sorted(CASES))
def test_guard_refuses_a_missing_input(module):
    call, exc, what = CASES[module]()
    assert_refuses_missing_input(call, exc=exc, what=f"{module}: {what}")


def test_every_guard_is_enrolled():
    """A new guard is enrolled by EXISTING, not by somebody remembering.

    This is the check that keeps the contract from becoming the honour system
    it replaced: the enrolment list is compared against what the codebase
    actually contains, and an exemption has to state its reason.
    """
    discovered = set(discover_guard_modules())
    covered = set(CASES) | set(NOT_INPUT_GUARDS)
    missing = sorted(discovered - covered)
    assert not missing, (
        f"guard modules with no missing-input contract test: {missing}. "
        f"Add a case to CASES, or an explained exemption to NOT_INPUT_GUARDS "
        f"in guard_contract.py — 'exempt' must never be the quiet default.")


def test_the_enrolment_check_can_actually_fail():
    """The guard on the guards, guarded.

    S47 was a test that proved a guard fires and had never made it fire. If
    `discover_guard_modules` silently found nothing, `test_every_guard_is_
    enrolled` would pass forever while checking nothing at all.
    """
    found = discover_guard_modules()
    assert len(found) >= 10, (
        f"discovery found only {len(found)} guard modules; the enrolment "
        f"check is passing because it is looking at an empty set")
    assert "multiplicity" in found and "execution_boundary" in found


def test_a_guard_that_returns_instead_of_refusing_fails_the_contract():
    """The template itself must reject a quiet degrade, not just a wrong type."""
    class Nope(RuntimeError):
        pass

    with pytest.raises(AssertionError, match="instead of refusing"):
        assert_refuses_missing_input(lambda: None, exc=Nope, what="probe")

    with pytest.raises(AssertionError, match="rather than"):
        assert_refuses_missing_input(
            lambda: (_ for _ in ()).throw(ValueError("boom")),
            exc=Nope, what="probe")
