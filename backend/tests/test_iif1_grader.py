"""The grader's contract: no outcome without a licence, no Brier without a base rate.

The whole harness is built and tested before a single campaign record resolves
(first on 2026-08-21), which is the point — grade-readiness precedes accrual-
readiness, and forty nights bought against a statistic nobody has written down
buys receipts rather than evidence.

So these tests do two jobs. They check the arithmetic on synthetic data, and
they check the REFUSALS, which are the part that has to hold on a morning when
somebody wants a number.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.services import investigator_night as N
from backend.services import iif1_grader as G


# ── a small synthetic world ────────────────────────────────────────────────
def _receipt(night: str, t0: float, *, version: int | None = 2,
             n_cells: int = 4, sandbox: bool = False, status: str = "ok"):
    rows_by_arm = {}
    for arm in N.ARMS:
        rows_by_arm[arm] = {"rows": [
            {"arm": arm, "ticker": f"T{i}", "arm_started_at": t0 + i,
             "arm_finished_at": t0 + i + 10} for i in range(n_cells)]}
    r = {"night": night, "status": status, "sandbox": sandbox,
         "per_arm": rows_by_arm, "elapsed_s": 600.0,
         "decision_lag_minutes": 10.0, "calls": 100,
         "tickers": [f"T{i}" for i in range(n_cells)]}
    if version is not None:
        r["implementation_version"] = version
        r["arm_implementation_fingerprint"] = "abc123"
    return r


def _record(night_made_at: str, arm: str, ticker: str, prob: float,
            outcome: int | None = None, *, observable="abs_move_exceeds",
            horizon=5, threshold=0.05, population="synthetic"):
    return {"prediction_id": f"{arm}-{ticker}-{threshold}",
            "arm": arm, "ticker": ticker, "observable": observable,
            "horizon_days": horizon, "threshold": threshold,
            "probability": prob, "outcome": outcome,
            "made_at": night_made_at, "evidence_population": population}


@pytest.fixture
def world(tmp_path):
    """Two nights, five arms, four tickers, outcomes supplied."""
    rd = tmp_path / "nights"
    rd.mkdir()
    base = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    made = {}
    for i, night in enumerate(("2026-09-01", "2026-09-02")):
        t0 = base + i * 86400
        (rd / f"{night}.json").write_text(json.dumps(_receipt(night, t0)),
                                          encoding="utf-8")
        made[night] = datetime.fromtimestamp(t0 + 3 + 10,
                                             timezone.utc).isoformat()
    return {"receipts": rd, "made_at": made}


def _records_for(world, *, treatment_edge: float = 0.0, seed: int = 7):
    """B_tools shifted toward the truth by `treatment_edge`."""
    rng = __import__("random").Random(seed)
    out = []
    for night, made in world["made_at"].items():
        for i in range(4):
            y = 1 if rng.random() < 0.4 else 0
            base = 0.35 + 0.1 * rng.random()
            for arm in N.ARMS:
                p = base
                if arm == G.PRIMARY_TREATMENT:
                    p = min(0.98, max(0.02, base + treatment_edge * (1 if y else -1)))
                out.append(_record(made, arm, f"T{i}", round(p, 4), y))
    return out


# ── the two access modes, enforced by deletion ─────────────────────────────
def test_power_mode_physically_cannot_see_an_outcome(tmp_path, world):
    """§64's freedom is only real if 'consumes no outcome' is a property of the
    code. A comment saying so is the honour system."""
    ledger = tmp_path / "led.jsonl"
    recs = _records_for(world)
    for r in recs:
        r["evidence_population"] = G.CAMPAIGN_POPULATION
    ledger.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")

    loaded = G.load_records(ledger, mode=G.MODE_POWER)
    assert loaded, "fixture produced no records"
    for f in G.OUTCOME_FIELDS:
        assert all(f not in r for r in loaded), (
            f"{f} survived the power-mode load; the power path could read an "
            f"outcome and nothing would notice")

    graded = G.load_records(ledger, mode=G.MODE_GRADE)
    assert any("outcome" in r for r in graded)


# ── night attribution ──────────────────────────────────────────────────────
def test_records_are_attributed_by_measured_interval(world):
    recs = G.attach_night(_records_for(world), world["receipts"])
    nights = {r["night"] for r in recs}
    assert nights == {"2026-09-01", "2026-09-02"}
    assert all(r["implementation_version"] == 2 for r in recs)


def test_an_orphan_record_is_refused_not_nearest_matched(world):
    """Assigning to the nearest night would cross the implementation_version
    boundary silently, which is the one thing the boundary exists to prevent."""
    orphan = _record("2025-01-01T00:00:00+00:00", "A_snapshot", "T0", 0.5, 1)
    with pytest.raises(G.GradeRefused, match="matches 0 night"):
        G.attach_night([orphan], world["receipts"])


def test_an_unstamped_receipt_is_labelled_not_assumed(tmp_path):
    """Night 1's receipt predates the version stamp. Filling the hole with the
    version we BELIEVE it ran turns an inference into a record."""
    rd = tmp_path / "n"
    rd.mkdir()
    t0 = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).timestamp()
    (rd / "2026-08-17.json").write_text(
        json.dumps(_receipt("2026-08-17", t0, version=None)), encoding="utf-8")
    made = datetime.fromtimestamp(t0 + 13, timezone.utc).isoformat()
    recs = G.attach_night([_record(made, "A_snapshot", "T0", 0.5, 1)], rd)
    assert recs[0]["implementation_version"] == G.UNSTAMPED_VERSION
    assert recs[0]["implementation_version"] != 1


def test_no_receipts_means_no_attribution_and_it_refuses(tmp_path):
    with pytest.raises(G.GradeRefused, match="no night receipts"):
        G.attach_night([_record("2026-09-01T10:00:13+00:00", "A_snapshot",
                                "T0", 0.5, 1)], tmp_path / "empty")


# ── pairing ────────────────────────────────────────────────────────────────
def test_a_cell_missing_from_one_arm_is_dropped_from_all(world):
    recs = G.attach_night(_records_for(world), world["receipts"])
    before = G.pair_cells(recs)
    # Kill exactly one cell on one arm — the Night-1 failure mode.
    victim = next(r for r in recs
                  if r["arm"] == "B_tools" and r["ticker"] == "T0"
                  and r["night"] == "2026-09-01")
    after = G.pair_cells([r for r in recs if r is not victim])
    assert after["n_cells_paired"] == before["n_cells_paired"] - 1
    assert after["n_cells_dropped_unpaired"] == 1
    # And the accounting names WHICH arm lost it, because a failure available
    # only to the tool arms is a bias with a direction, toward the null.
    assert after["per_arm"]["B_tools"]["n_missing_from_arm"] == 1
    assert after["per_arm"]["A_snapshot"]["n_dropped_for_pairing"] == 1


# ── Brier and its base rate are one object ─────────────────────────────────
def test_brier_cannot_be_obtained_without_its_base_rate():
    out = G.brier_with_base_rate([0.2, 0.8, 0.5, 0.5], [0, 1, 1, 0])
    assert "base_rate" in out and "brier" in out
    assert out["base_rate"] == pytest.approx(0.5)
    assert out["brier"] == pytest.approx((0.04 + 0.04 + 0.25 + 0.25) / 4)


def test_a_degenerate_base_rate_is_refused():
    """p(1-p) = 0: no skill score is defined and the MDE is infinite. A Brier
    computed anyway is a fact about the sample, read as one about the model."""
    with pytest.raises(G.GradeRefused, match="base rate is"):
        G.brier_with_base_rate([0.1, 0.2, 0.3], [0, 0, 0])
    with pytest.raises(G.GradeRefused, match="base rate is"):
        G.brier_with_base_rate([0.9, 0.8], [1, 1])


def test_an_empty_brier_is_refused_not_zero():
    with pytest.raises(G.GradeRefused, match="no scored records"):
        G.brier_with_base_rate([], [])


def test_murphy_decomposition_closes_exactly_on_discrete_forecasts():
    """BS = reliability - resolution + uncertainty. The identity holds exactly
    only when every forecast inside a bin is identical, so it is asserted where
    it is actually true — on discrete forecasts that land one per bin."""
    rng = __import__("random").Random(3)
    probs = [rng.choice([0.05, 0.25, 0.45, 0.65, 0.85]) for _ in range(300)]
    ys = [1 if rng.random() < p else 0 for p in probs]
    out = G.brier_with_base_rate(probs, ys)
    assert out["murphy_closes_exactly"] is True
    assert abs(out["binning_residual"]) < 1e-9


def test_continuous_forecasts_leave_a_named_binning_residual():
    """And it is NAMED. A binning artefact reported as an unexplained residual
    is the sort of number a reader talks themselves into ignoring."""
    rng = __import__("random").Random(3)
    probs = [round(rng.random(), 3) for _ in range(200)]
    ys = [1 if rng.random() < p else 0 for p in probs]
    out = G.brier_with_base_rate(probs, ys)
    assert out["murphy_closes_exactly"] is False
    assert 0 < abs(out["binning_residual"]) < 0.01
    assert out["n_bins"] >= 2


def test_the_climatology_reference_is_never_the_scored_outcomes():
    """Scoring against the sample's own base rate grades a forecaster on its own
    answer key. The reference is supplied from history or there is no skill
    claim at all — and the default says so instead of inventing one."""
    out = G.brier_with_base_rate([0.5, 0.5], [1, 0])
    assert out["brier_skill_score"] is None
    assert "NOT SUPPLIED" in out["bss_reference"]
    with_clim = G.brier_with_base_rate([0.5, 0.5], [1, 0], climatology=0.3)
    assert with_clim["brier_skill_score"] is not None
    assert "historical population" in with_clim["bss_reference"]


def test_a_rare_event_brier_looks_good_and_the_base_rate_says_why():
    """The trap the base-rate requirement exists for: forecasting the base rate
    everywhere scores well and has zero resolution."""
    ys = [1] * 4 + [0] * 96
    out = G.brier_with_base_rate([0.04] * 100, ys, climatology=0.04)
    assert out["brier"] < 0.04                     # looks excellent
    assert out["resolution"] == pytest.approx(0.0, abs=1e-9)   # knows nothing
    assert out["brier_skill_score"] == pytest.approx(0.0, abs=1e-9)


# ── the paired contrast: the unit is the night ─────────────────────────────
def test_the_contrast_treats_nights_as_the_sample_not_records(world):
    recs = G.attach_night(_records_for(world, treatment_edge=0.15),
                          world["receipts"])
    c = G.paired_brier_contrast(G.pair_cells(recs))
    assert c["n_nights"] == 2
    assert c["n_paired_cells"] == 8
    assert len(c["per_night_mean_diff"]) == 2
    # n_effective counts DATE BLOCKS, never rows.
    assert c["se_iid"] == pytest.approx(
        abs(c["per_night_mean_diff"][0] - c["per_night_mean_diff"][1]) / 2,
        rel=1e-6)


def test_the_sign_convention_is_treatment_minus_control(world):
    """A negative difference means the treatment scored a LOWER Brier. The read
    gate's terminal rule is written on B_tools - A_snapshot, and flipping it is
    a way to be exactly wrong while every number looks reasonable."""
    recs = G.attach_night(_records_for(world, treatment_edge=0.25),
                          world["receipts"])
    c = G.paired_brier_contrast(G.pair_cells(recs))
    assert c["treatment"] == "B_tools" and c["control"] == "A_snapshot"
    assert c["mean_diff"] < 0, "an informed treatment must score lower"
    assert c[c["treatment"]]["brier"] < c[c["control"]]["brier"]


def test_one_night_yields_no_standard_error(tmp_path):
    """A standard error over one date block is undefined, not small."""
    rd = tmp_path / "n"
    rd.mkdir()
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    (rd / "2026-09-01.json").write_text(json.dumps(_receipt("2026-09-01", t0)),
                                        encoding="utf-8")
    made = datetime.fromtimestamp(t0 + 13, timezone.utc).isoformat()
    recs = []
    for i in range(4):
        for arm in N.ARMS:
            recs.append(_record(made, arm, f"T{i}", 0.4 + 0.01 * i, i % 2))
    c = G.paired_brier_contrast(G.pair_cells(G.attach_night(recs, rd)))
    assert c["n_nights"] == 1
    assert c["se_used"] is None and c["t_stat"] is None


def test_a_cell_with_two_different_outcomes_is_refused(world):
    recs = G.attach_night(_records_for(world), world["receipts"])
    for r in recs:
        if r["arm"] == "B_tools":
            r["outcome"] = 1 - int(r["outcome"])
    with pytest.raises(G.GradeRefused, match="resolved to"):
        G.paired_brier_contrast(G.pair_cells(recs))


def test_nothing_resolved_is_a_state_not_a_null(world):
    recs = G.attach_night(_records_for(world), world["receipts"])
    for r in recs:
        r["outcome"] = None
    with pytest.raises(G.GradeRefused, match="no paired cell has an outcome"):
        G.paired_brier_contrast(G.pair_cells(recs))


# ── §64 forward power, consuming no outcome ────────────────────────────────
def test_forward_mde_consumes_no_outcome_and_says_so(world):
    recs = G.attach_night(_records_for(world, treatment_edge=0.1),
                          world["receipts"])
    deltas = G.forecast_deltas_by_night(G.pair_cells(recs))
    m = G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                             n_nights_target=40)
    assert m["consumed_outcomes"] is False
    assert m["mde"] > 0
    assert m["basis"] == "OPTIMISTIC_FLOOR_INDEPENDENT_OUTCOMES"


def test_identical_arms_are_undetectable_at_every_n(world):
    """THE REFUSAL WORTH THE WHOLE FUNCTION. If the arms never disagree the
    paired difference is exactly zero whatever the world does, and no sample
    size fixes it. That is a property of the treatment, and it is knowable for
    $0 on the night the forecasts are minted."""
    recs = G.attach_night(_records_for(world, treatment_edge=0.0),
                          world["receipts"])
    deltas = G.forecast_deltas_by_night(G.pair_cells(recs))
    assert all(all(d == 0 for d in v) for v in deltas.values())
    with pytest.raises(G.GradeRefused, match="IDENTICAL"):
        G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                             n_nights_target=40)


def test_the_mde_shrinks_as_the_square_root_of_the_nights(world):
    recs = G.attach_night(_records_for(world, treatment_edge=0.1),
                          world["receipts"])
    deltas = G.forecast_deltas_by_night(G.pair_cells(recs))
    a = G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                             n_nights_target=40)["mde"]
    b = G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                             n_nights_target=160)["mde"]
    assert a / b == pytest.approx(2.0, rel=1e-6)


def test_declared_intra_night_correlation_only_ever_widens_the_mde(world):
    """rho=0 is a FLOOR. Cells within a night share a market, so the honest
    number is larger, and a declared rho must not be able to shrink it."""
    recs = G.attach_night(_records_for(world, treatment_edge=0.1),
                          world["receipts"])
    deltas = G.forecast_deltas_by_night(G.pair_cells(recs))
    floor = G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                                 n_nights_target=40)
    infl = G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.3,
                                n_nights_target=40, outcome_correlation=0.3)
    assert infl["mde"] > floor["mde"]
    assert infl["basis"] == "DECLARED_INTRA_NIGHT_CORRELATION"


def test_a_degenerate_base_rate_has_no_forward_mde(world):
    recs = G.attach_night(_records_for(world, treatment_edge=0.1),
                          world["receipts"])
    deltas = G.forecast_deltas_by_night(G.pair_cells(recs))
    with pytest.raises(G.GradeRefused, match="not strictly between"):
        G.forward_mde_paired(deltas_by_night=deltas, base_rate=0.0,
                             n_nights_target=40)


# ── the read gate ──────────────────────────────────────────────────────────
def test_the_graded_night_count_is_counted_not_accepted(tmp_path):
    """`check_read` takes n as an INPUT — the last honour-system item on the
    canon's list. Nothing in this repo may supply it from anywhere but a count."""
    rd = tmp_path / "n"
    rd.mkdir()
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    for i, night in enumerate(("2026-09-01", "2026-09-02", "2026-09-03")):
        (rd / f"{night}.json").write_text(
            json.dumps(_receipt(night, t0 + i * 86400)), encoding="utf-8")
    # A sandbox night and a void night are not graded nights.
    (rd / "2026-09-04.json").write_text(
        json.dumps(_receipt("2026-09-04", t0, sandbox=True)), encoding="utf-8")
    (rd / "2026-09-05.json").write_text(
        json.dumps(_receipt("2026-09-05", t0, status="void")), encoding="utf-8")
    assert G.derive_n_graded_nights(rd) == 3


def test_an_unlicensed_read_is_refused(tmp_path):
    rd = tmp_path / "n"
    rd.mkdir()
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    (rd / "2026-09-01.json").write_text(json.dumps(_receipt("2026-09-01", t0)),
                                        encoding="utf-8")
    with pytest.raises(G.GradeRefused):
        G.assert_read_licensed(rd)


def test_a_missing_read_gate_refuses_rather_than_reimplementing_it(tmp_path):
    """A second copy of the read schedule is a second thing that can drift."""
    lic = G.check_read_licence(tmp_path / "n", module_root=tmp_path / "nope")
    assert lic["licensed"] is False
    assert lic["disposition"] == "GATE_UNREADABLE"


# ── the synthetic path may not touch the campaign ──────────────────────────
def test_synthetic_grading_refuses_a_real_campaign_record(world):
    """The one path with no read licence must not be usable to read the real
    thing early. A test flag is not a licence."""
    recs = G.attach_night(_records_for(world, treatment_edge=0.1),
                          world["receipts"])
    for r in recs:
        r["evidence_population"] = G.CAMPAIGN_POPULATION
    with pytest.raises(G.GradeRefused, match="unlicensed read wearing a test"):
        G.grade_synthetic(recs)


def test_the_whole_pipeline_runs_end_to_end_on_synthetic_outcomes(world):
    """What makes the harness ready before 2026-08-21: everything from pairing
    through the Murphy decomposition runs, and no campaign record is read."""
    recs = G.attach_night(_records_for(world, treatment_edge=0.2),
                          world["receipts"])
    rep = G.grade_synthetic(recs, climatology=0.35)
    assert rep["read_licence"]["disposition"] == "SYNTHETIC_ONLY"
    assert rep["pooled"]["n_nights"] == 2
    assert rep["pooled"]["mean_diff"] < 0
    # Within version AND pooled, per Order 15 §2.
    assert "2" in rep["by_implementation_version"]
    for arm in (G.PRIMARY_TREATMENT, G.PRIMARY_CONTROL):
        assert "base_rate" in rep["pooled"][arm]
        assert rep["pooled"][arm]["brier_skill_score"] is not None


# ── climatology from data, not from an assertion ───────────────────────────
def test_climatology_is_measured_from_a_panel_not_supplied_as_a_number():
    panel = {"A": [0.02] * 10, "B": [-0.001] * 10}
    out = G.climatological_base_rate(panel, horizon_days=5, threshold=0.05)
    # A: 5 x +2% compounds past +5% every window. B never moves.
    assert out["base_rate"] == pytest.approx(0.5)
    assert out["basis"] == "MEASURED_FROM_SUPPLIED_RETURNS_PANEL"


def test_an_empty_panel_is_refused_not_a_base_rate_of_zero():
    with pytest.raises(G.GradeRefused, match="not a base rate of zero"):
        G.climatological_base_rate({"A": [0.01]}, horizon_days=5,
                                   threshold=0.05)


# ── intra-night correlation, measured rather than declared ─────────────────
def test_perfectly_coupled_names_measure_rho_near_one():
    """Every name moving together on the same days is rho = 1 by construction.
    If the estimator cannot recover that, it cannot be trusted on real data."""
    days = [0.10 if i % 3 == 0 else 0.001 for i in range(300)]
    panel = {f"T{j}": list(days) for j in range(10)}
    out = G.measure_intra_night_correlation(panel, horizon_days=1,
                                            threshold=0.03)
    # `p` is estimated from the same data, so the point estimate lands a
    # little above 1. That is why `rho_for_use` is clamped: a design effect
    # cannot exceed the number of names.
    assert out["rho_measured"] == pytest.approx(1.0, abs=0.01)
    assert out["rho_measured"] > 1.0 and out["capped_at_one"] is True
    assert out["rho_for_use"] == 1.0
    assert out["design_effect_at_m"] == pytest.approx(10.0, abs=1e-6)


def test_independent_names_measure_rho_near_zero():
    rng = __import__("random").Random(5)
    panel = {f"T{j}": [0.10 if rng.random() < 0.2 else 0.001
                       for _ in range(2000)] for j in range(20)}
    out = G.measure_intra_night_correlation(panel, horizon_days=1,
                                            threshold=0.03)
    assert abs(out["rho_measured"]) < 0.05


def test_a_negative_rho_is_reported_but_floored_for_use():
    """A measurement may only ever make this guard MORE conservative. A
    negative intraclass correlation would shrink the MDE, so it is reported as
    measured and floored at zero where it is used."""
    # Anti-coupled: exactly one name exceeds each day, in rotation.
    n_names, n_days = 5, 400
    panel = {f"T{j}": [0.10 if (i % n_names) == j else 0.001
                       for i in range(n_days)] for j in range(n_names)}
    out = G.measure_intra_night_correlation(panel, horizon_days=1,
                                            threshold=0.03)
    assert out["rho_measured"] < 0
    assert out["rho_for_use"] == 0.0
    assert out["floored_at_zero"] is True


def test_one_name_has_no_cross_section_to_correlate():
    """Returning 0 would read as 'measured, and they are independent'."""
    with pytest.raises(G.GradeRefused, match="at least two names"):
        G.measure_intra_night_correlation({"A": [0.01] * 50}, horizon_days=1,
                                          threshold=0.03)


# ── the power report is PER REGISTERED CELL ────────────────────────────────
def _campaign_ledger(tmp_path, world, *, cells):
    recs = []
    for night, made in world["made_at"].items():
        for i in range(4):
            for (obs, h, thr) in cells:
                for j, arm in enumerate(N.ARMS):
                    # The arms must DISAGREE or the identical-arms refusal
                    # fires — correctly. Caught by that guard on first run.
                    recs.append(_record(made, arm, f"T{i}",
                                        round(0.3 + 0.05 * i + 0.02 * j, 4),
                                        None, observable=obs, horizon=h,
                                        threshold=thr,
                                        population=G.CAMPAIGN_POPULATION))
    p = tmp_path / "led.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    return p


def test_a_cell_with_no_measured_base_rate_is_refused(tmp_path, world):
    """A default here would be an assertion about how often the world moves,
    silently setting the power of the trial. This refusal caught a real error:
    a climatology measured for (h=5, thr=0.03), a cell that does not exist."""
    cells = [("abs_move_exceeds", 1, 0.03), ("abs_move_exceeds", 5, 0.05)]
    led = _campaign_ledger(tmp_path, world, cells=cells)
    with pytest.raises(G.GradeRefused, match="no measured base rate"):
        G.power_report(ledger=led, receipts_dir=world["receipts"],
                       base_rates={("abs_move_exceeds", 5, 0.05): 0.196})


def test_each_registered_cell_gets_its_own_mde(tmp_path, world):
    """Night 1's two thresholds have measured base rates 0.097 and 0.196 — a
    factor of two apart. One pooled MDE across them is correct arithmetic
    against the wrong world."""
    cells = [("abs_move_exceeds", 1, 0.03), ("abs_move_exceeds", 5, 0.05)]
    led = _campaign_ledger(tmp_path, world, cells=cells)
    rep = G.power_report(
        ledger=led, receipts_dir=world["receipts"],
        base_rates={("abs_move_exceeds", 1, 0.03): 0.0972,
                    ("abs_move_exceeds", 5, 0.05): 0.1963})
    by_cell = rep["forward_mde_by_cell"]
    assert len(by_cell) == 2
    assert {m["base_rate"] for m in by_cell.values()} == {0.0972, 0.1963}
    # And the power path still could not have seen an outcome.
    assert all(m["consumed_outcomes"] is False for m in by_cell.values())
