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


def _case_population():
    from backend.services.research_gym.population import (
        NoPopulationInScope, assess_population)
    # The failure this guard exists for: a universe asserted rather than
    # counted. Handed no counts it must refuse, because a declared population
    # is exactly the honour-system input that produced std_turn's phantom cell.
    return (lambda: assess_population("a universe nobody counted", None),
            NoPopulationInScope, "a population claimed with no counts behind it")


def _case_night_launcher():
    import tempfile, pathlib
    from backend.services.night_launcher import LaunchRefused, evaluate_launch
    # A launch-receipt directory that CANNOT EXIST: its parent is a file. The
    # missing input is the launcher's own evidence channel, and the refusal
    # matters because every other property of this launcher — acceptance, the
    # morning check, telling a refusing launcher from a dead task — is read
    # back out of those receipts. A run whose evidence may not exist is worse
    # than a night not run.
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "blocker").write_text("not a directory", encoding="utf-8")
    return (lambda: evaluate_launch(launch_dir=d / "blocker" / "receipts"),
            LaunchRefused, "a launcher whose receipts cannot be written")


def _case_iif1_grader():
    from backend.services.iif1_grader import GradeRefused, brier_with_base_rate
    # A Brier over a sample whose base rate is 0. `p(1-p)` is zero, no skill
    # score is defined and the MDE is infinite — the score computed anyway is a
    # fact about the sample's degeneracy that reads as one about the forecaster.
    # This is the rare-event trap in its purest form, and the grader exists to
    # print a base rate beside every Brier precisely so it cannot be missed.
    return (lambda: brier_with_base_rate([0.1, 0.2, 0.3], [0, 0, 0]),
            GradeRefused, "a Brier over a sample with no positive outcomes")


def _case_spread_estimators():
    from backend.services.spread_estimators import (SpreadConventionError,
                                                    SpreadEstimate)
    # The missing input is the CONVENTION, and it is the one whose absence
    # looks exactly like agreement: every convention yields a positive number
    # of basis points, so a wrong one produces a plausible cost, a plausible
    # net return and a plausible survivor count, and nothing downstream can
    # tell. A spread and the convention it is quoted in are one object here.
    return (lambda: SpreadEstimate(value=0.001, convention="", estimator="t",
                                   n_obs=100),
            SpreadConventionError, "a spread with no declared convention")


def _case_research_daemon():
    from backend.services.research_daemon import (HypothesisJob, JobRefused,
                                                  power_screen)
    # A job with no standard error. Without one there is no MDE, and without an
    # MDE a null result is a statement about the instrument rather than the
    # world (§19) — and the job cannot be prioritised either, because expected
    # value is meaningless without knowing whether it can resolve at all.
    job = HypothesisJob(
        hypothesis_id="H", question="q", universe="u", outcome="o",
        start="2010-01-01", end="2015-01-01", n_date_blocks=60,
        se_per_block=0.0, expected_effect=0.02, effect_units="annualised")
    return (lambda: power_screen(job), JobRefused,
            "a job power-screened with no standard error")


def _case_net_dataset():
    from backend.services.net_dataset import LabelRefused, cross_sectional_rank
    # A cross-sectional rank over ONE name. It is 0.5 by construction — a fact
    # about the arithmetic rather than about the security — and a panel that
    # quietly emits it teaches a network that thin dates are average.
    return (lambda: cross_sectional_rank({"ONLY": 0.1}), LabelRefused,
            "a cross-sectional rank with no cross-section")


def _case_cost_model():
    from backend.services.cost_model import CostRefused, verdict_across_band
    # The missing input is the PROVENANCE. A bare float carries no record of
    # whether it was measured or declared, and one call downstream the two are
    # indistinguishable — which is the whole failure Order 18 §1 rules on: the
    # floor value used as a cost looks exactly like a measured cost.
    return (lambda: verdict_across_band(lambda bps: bps > 3.0, 5.0),
            CostRefused, "a verdict priced off a bare float with no provenance")


def _case_taq_calibration():
    from backend.services.taq_calibration import TaqRefused, reading_for
    # The missing input is COVERAGE of the NAME. Entitlement is a fact about a
    # subscription; a retired band is a fact about a name. A panel that never
    # covered this ticker must not fall back to a panel-wide average, because
    # the fallback would retire a declared band on the strength of other
    # people's liquidity.
    return (lambda: reading_for([{"ticker": "AAPL", "date": "2026-08-14",
                                  "n_quotes": 500_000, "mean_bps": 1.0,
                                  "median_bps": 1.0, "mid": 230.0}], "PLUG"),
            TaqRefused, "a TAQ cost for a name the panel never covered")


def _case_instrument_floor():
    from backend.services.instrument_floor import (Instrument,
                                                   InstrumentUnresolvable,
                                                   profile_instrument)
    # The missing input is RESOLUTION. An instrument that cannot produce a
    # finite reading on null data has no measurable floor, and profiling it
    # anyway would emit a null band derived from a handful of survivors — which
    # licenses every reading above it as a detection.
    def _always_broken(_d):
        raise ValueError("no reading")

    inst = Instrument(name="broken", read=_always_broken,
                      generate=lambda t, n, rng: (t, n, rng),
                      null_truth=0.0, units="u", truths=(1.0,), n_default=20,
                      basis="constructed", consumers=("test",))
    return (lambda: profile_instrument(inst, sims=40),
            InstrumentUnresolvable, "a floor profiled with no finite reading")


def _case_lane_autopsy():
    from backend.services.lane_autopsy import (CONVICTION_RULES, ReplayRefused,
                                               replay)
    import pandas as pd
    # The missing input is a PRICE COLUMN. A name with no prices lets the
    # remaining weights re-normalise, which shows up as a return rather than as
    # an error — survivorship arriving through the back door.
    px = pd.DataFrame({"A": [100.0, 101.0, 102.0]},
                      index=pd.bdate_range("2026-06-08", periods=3))
    return (lambda: replay(px, {"A": 1, "GONE": 1}, CONVICTION_RULES),
            ReplayRefused, "a replay over a name with no prices")


def _case_net_panel():
    from pathlib import Path

    from backend.services.net_panel import PanelRefused, load_price_panel
    # The missing input is the SOURCE ITSELF. A materializer that defaults an
    # absent price file to an empty panel hands the tournament a dataset that
    # looks like a dataset — every downstream number would be a fact about
    # nothing, formatted like a fact about the market.
    return (lambda: load_price_panel(Path("Z:/does/not/exist.parquet")),
            PanelRefused, "a panel materialized from an absent price source")


def _case_net_tournament():
    from pathlib import Path

    from backend.services.net_tournament import (TournamentRefused,
                                                 assert_signed)
    # The missing input is the AUTHORIZATION. The tournament runs a declared,
    # signed protocol or it does not run (canon §6) — an absent prereg read as
    # permission would be the most permissive answer a missing input can give.
    return (lambda: assert_signed(Path("Z:/does/not/exist.md")),
            TournamentRefused, "a tournament run with no pre-registration")


def _case_convexity_episodes():
    import numpy as np

    from backend.services.convexity_episodes import (EpisodeRefused,
                                                     arm_outcome)
    # The missing input is the OUTCOME WINDOW. An arm scored on a single
    # price has no path to manage; returning $1.00 for it would report
    # every management rule as exactly break-even — plausible, green, and
    # about nothing.
    return (lambda: arm_outcome(np.array([100.0]), "hold",
                                cost_one_way_bps=3.0,
                                ann_vol_at_crossing=0.3),
            EpisodeRefused, "an arm scored on a one-price outcome window")


def _case_relative_value_labels():
    from backend.services.cost_model import MEASURED_TAQ_QUOTED, OneWayBps
    from backend.services.relative_value_labels import (PairRefused,
                                                        pair_label)
    # The missing input is the RETURN. A pair labelled with an invented
    # forward return is a training row about nothing; the network cannot
    # tell it from a market fact, which is precisely why it must refuse
    # here rather than impute there.
    c = OneWayBps(1.0, MEASURED_TAQ_QUOTED, basis="test")
    return (lambda: pair_label(fwd_a=float("nan"), fwd_b=0.01, dd_a=None,
                               dd_b=None, cost_a=c, cost_b=c),
            PairRefused, "a pair labelled from an invented return")


CASES = {
    "lane_autopsy": _case_lane_autopsy,
    "net_panel": _case_net_panel,
    "net_tournament": _case_net_tournament,
    "convexity_episodes": _case_convexity_episodes,
    "relative_value_labels": _case_relative_value_labels,
    "instrument_floor": _case_instrument_floor,
    "taq_calibration": _case_taq_calibration,
    "cost_model": _case_cost_model,
    "net_dataset": _case_net_dataset,
    "research_daemon": _case_research_daemon,
    "spread_estimators": _case_spread_estimators,
    "iif1_grader": _case_iif1_grader,
    "night_launcher": _case_night_launcher,
    "population": _case_population,
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
