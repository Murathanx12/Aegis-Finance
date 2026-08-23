"""The registry must see populations nobody remembered to register.

The bug being guarded: on 2026-08-23 the deploy read DEGRADED because
`live_forward` had been quiet 11 days, and that was read as the learning engine
having stopped -- while `arena_forward`, a different file entirely, was writing
normally. It was invisible because no surface enumerated it.

So the load-bearing test here is `test_every_ledger_on_disk_is_claimed`: a new
`predictions.jsonl` that nobody adds to `_POPULATIONS` FAILS, rather than going
quietly unmonitored the way the arena's did.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import forecast_populations as FP


def _rec(pid: str, made_at: str, horizon: int = 20,
         outcome=None) -> dict:
    """Built through the REAL factory so the fixture cannot drift.

    The first cut of this helper hand-rolled a dict and omitted `model`, which
    made every health row read UNREADABLE — a fixture that silently disagreed
    with the schema it was pretending to test.
    """
    from dataclasses import asdict

    from backend.services.belief_state import Observable, make_prediction

    rec = make_prediction(
        ticker="AAPL", specialist="test",
        observable=Observable.BEATS_BENCHMARK,
        horizon_days=horizon, probability=0.5,
        thesis="fixture", counter_thesis="fixture",
        next_observable="fixture", model="test-model",
        model_version="1", prompt="p", input_snapshot={"x": 1},
        benchmark="SPY", made_at=datetime.fromisoformat(made_at).isoformat(
            timespec="seconds"))
    d = asdict(rec)
    d["prediction_id"] = pid
    d["outcome"] = outcome
    return d


def _write(path, recs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs),
                    encoding="utf-8")


# --------------------------------------------------------------- registry


def test_registry_lists_all_three_populations():
    ids = FP.known_ids()
    assert set(ids) == {"campaign_forward", "live_forward", "arena_forward"}


def test_arena_population_is_registered_and_points_at_the_arena_file():
    """The whole point: the arena's ledger is a first-class population."""
    pop = FP.get("arena_forward")
    assert pop.relative_path == "arena/predictions.jsonl"
    assert "pi_arena_daily" in pop.producer


def test_every_population_declares_producer_consumers_and_purpose():
    for pop in FP.all_populations():
        assert pop.producer, f"{pop.population_id} has no producer"
        assert pop.consumers, f"{pop.population_id} names no consumer"
        assert pop.purpose, f"{pop.population_id} has no purpose"


def test_campaign_reads_the_REPO_ledger_not_the_volume():
    """Caught only by thinking about prod: locally the two bases coincide.

    The campaign's history is a REPOSITORY artifact and must not follow a
    volume mount around (`evidence_population.ledger_dir`). A registry that
    hard-coded one base would report the volume's file as the campaign's in
    production while looking perfectly correct on every dev machine.
    """
    assert FP.get("campaign_forward").base == "legacy"
    assert FP.get("live_forward").base == "ledger"
    assert FP.get("arena_forward").base == "ledger"


def test_population_paths_match_evidence_population():
    """The two modules must not disagree about where a ledger lives."""
    from backend.services import evidence_population as EP
    assert FP.get("campaign_forward").path() == EP.ledger_path(
        EP.EvidencePopulation.CAMPAIGN_FORWARD)
    assert FP.get("live_forward").path() == EP.ledger_path(
        EP.EvidencePopulation.LIVE_FORWARD)


def test_unknown_population_is_refused_not_guessed():
    with pytest.raises(FP.UnknownPopulation):
        FP.get("some_ledger_someone_invented")


def test_reading_without_naming_a_population_is_refused():
    with pytest.raises(FP.PopulationNotNamed):
        FP.assert_named(None, consumer="G7 gate")
    with pytest.raises(FP.PopulationNotNamed):
        FP.assert_named("", consumer="G7 gate")


def test_pooling_two_populations_is_refused():
    with pytest.raises(FP.PopulationPoolingRefused):
        FP.refuse_pooling("live_forward", "arena_forward")
    # One population repeated is not pooling.
    FP.refuse_pooling("live_forward", "live_forward")


# ------------------------------------------------------------ health rows


def test_absent_file_reports_ABSENT_not_ok(tmp_path):
    row = FP.health("arena_forward", root=tmp_path)
    assert row["status"] == "ABSENT"
    assert row["exists"] is False
    assert row["n_records"] == 0


def test_absent_is_distinguished_from_empty(tmp_path):
    """A producer that ran and had nothing to say != nothing ever wrote here."""
    absent = FP.health("arena_forward", root=tmp_path)
    (tmp_path / "arena").mkdir(parents=True)
    (tmp_path / "arena" / "predictions.jsonl").write_text("", encoding="utf-8")
    empty = FP.health("arena_forward", root=tmp_path)
    assert absent["status"] == "ABSENT"
    assert empty["status"] != "ABSENT"


def test_fresh_arena_ledger_is_ok(tmp_path):
    today = date(2026, 8, 23)
    _write(tmp_path / "arena" / "predictions.jsonl",
           [_rec("a1", "2026-08-21T22:45:00+00:00")])
    row = FP.health("arena_forward", root=tmp_path, today=today)
    assert row["status"] == "ok", row
    assert row["population_id"] == "arena_forward"


def test_arena_quiet_clock_tolerates_a_weekend_but_not_an_outage(tmp_path):
    """5 days: a Sunday read of a Friday write must not alarm."""
    p = tmp_path / "arena" / "predictions.jsonl"
    _write(p, [_rec("a1", "2026-08-21T22:45:00+00:00")])       # Friday
    sunday = FP.health("arena_forward", root=tmp_path, today=date(2026, 8, 23))
    assert sunday["status"] == "ok", "a Sunday read of Friday's write alarmed"

    later = FP.health("arena_forward", root=tmp_path, today=date(2026, 8, 30))
    assert later["status"] != "ok", "a 9-day arena outage did not alarm"


def test_campaign_quiet_is_dormant_by_design_not_degraded(tmp_path):
    """The campaign is attended and bursty; silence ALONE is not a fault.

    The record is RESOLVED on purpose: an unresolved overdue record is a
    second, real problem, and the downgrade must apply only when quiet is the
    sole complaint. (The first version of this test used an unresolved record
    and caught exactly that — the row stayed DEGRADED, correctly.)
    """
    _write(tmp_path / "predictions.jsonl",
           [_rec("c1", "2026-01-01T00:00:00+00:00", outcome=1)])
    row = FP.health("campaign_forward", root=tmp_path, today=date(2026, 8, 23))
    assert row["status"] == "DORMANT_BY_DESIGN", row.get("problems")
    assert row["downgraded_from"] == "DEGRADED"
    assert row["dormant_reason"]


def test_campaign_overdue_is_excused_but_still_COUNTED(tmp_path):
    """The campaign's resolver is ATTENDED, so nobody running it today is a
    TODO, not an outage. The count must survive the downgrade — this changes
    the alarm, never the number."""
    _write(tmp_path / "predictions.jsonl",
           [_rec("c1", "2026-01-01T00:00:00+00:00", outcome=None)])
    row = FP.health("campaign_forward", root=tmp_path, today=date(2026, 8, 23))
    assert row["status"] == "DORMANT_BY_DESIGN", row
    assert row["n_overdue"] == 1, "the overdue count was hidden, not excused"
    assert row["problems"], "the problem text was dropped"


def test_the_SAME_data_still_alarms_on_live_forward(tmp_path):
    """The discriminating case: live_forward's resolver is SCHEDULED, so the
    identical record is a genuine fault there."""
    _write(tmp_path / "predictions.jsonl",
           [_rec("l1", "2026-01-01T00:00:00+00:00", outcome=None)])
    row = FP.health("live_forward", root=tmp_path, today=date(2026, 8, 23))
    assert row["status"] == "DEGRADED", row
    assert row["overdue_is_a_fault"] is True


def test_dormancy_excuses_only_the_declared_problems():
    """A population excuses what it is DECLARED dormant about, not everything."""
    campaign = FP.get("campaign_forward")
    assert FP._excused("5325 forecast(s) past due and unresolved", campaign)
    assert FP._excused("no new forecast in 200 days", campaign)
    assert not FP._excused("the ledger is corrupt", campaign)
    live = FP.get("live_forward")
    assert not FP._excused("5325 forecast(s) past due and unresolved", live)


def test_live_forward_quiet_IS_a_fault(tmp_path):
    """The live product's own accrual going quiet is a real problem."""
    _write(tmp_path / "predictions.jsonl",
           [_rec("l1", "2026-08-12T00:00:00+00:00")])
    row = FP.health("live_forward", root=tmp_path, today=date(2026, 8, 23))
    assert row["status"] != "ok"
    assert row["quiet_is_a_fault"] is True


# --------------------------------------------------------- registry health


def test_registry_health_names_which_population_is_bad(tmp_path):
    _write(tmp_path / "predictions.jsonl",
           [_rec("l1", "2026-08-12T00:00:00+00:00")])
    _write(tmp_path / "arena" / "predictions.jsonl",
           [_rec("a1", "2026-08-21T22:45:00+00:00")])
    reg = FP.registry_health(root=tmp_path, today=date(2026, 8, 23))

    assert reg["status"] == "DEGRADED"
    # The exact misreading this module exists to stop: the arena must NOT be
    # implicated by live_forward's silence.
    assert "arena_forward" not in reg["degraded_populations"]
    assert "live_forward" in reg["degraded_populations"]
    assert reg["populations"]["arena_forward"]["status"] == "ok"


def test_registry_health_refuses_to_pool():
    reg = FP.registry_health()
    assert "REFUSED" in reg["pooling"]
    # There must be no summed record count anywhere in the top level.
    assert "n_records" not in reg


def test_registry_reports_every_population_even_when_absent(tmp_path):
    reg = FP.registry_health(root=tmp_path, today=date(2026, 8, 23))
    assert reg["n_populations"] == len(FP.all_populations())
    assert set(reg["populations"]) == set(FP.known_ids())


# ------------------------------------------------- the enumeration guard


def test_every_ledger_on_disk_is_claimed_by_a_registered_population(tmp_path):
    """THE load-bearing test.

    A `predictions.jsonl` that no registered population claims is exactly how
    the arena's ledger stayed invisible. Simulate a new subsystem quietly
    adding one and assert the registry NOTICES rather than ignoring it.
    """
    _write(tmp_path / "predictions.jsonl", [_rec("l1", "2026-08-21T00:00:00+00:00")])
    _write(tmp_path / "arena" / "predictions.jsonl",
           [_rec("a1", "2026-08-21T00:00:00+00:00")])
    # A subsystem nobody registered starts writing forecasts.
    _write(tmp_path / "shadow_book" / "predictions.jsonl",
           [_rec("s1", "2026-08-21T00:00:00+00:00")])

    claimed = {(tmp_path / p.relative_path).resolve()
               for p in FP.all_populations()}
    on_disk = {p.resolve() for p in tmp_path.rglob("predictions.jsonl")}
    unclaimed = on_disk - claimed

    assert unclaimed, "fixture did not actually create an unregistered ledger"
    # This is the assertion a real unregistered ledger would trip.
    assert {p.name for p in unclaimed} == {"predictions.jsonl"}
    assert any("shadow_book" in str(p) for p in unclaimed)


def test_real_ledger_root_has_no_unregistered_population():
    """Run against the ACTUAL ledger root. Fails when a new ledger appears."""
    from backend import config as cfg
    root = cfg.OPTIMUS_LEDGER_DIR
    if not root.exists():
        pytest.skip("no ledger root on this machine")
    claimed = {(root / p.relative_path).resolve()
               for p in FP.all_populations()}
    on_disk = {p.resolve() for p in root.rglob("predictions.jsonl")}
    unclaimed = sorted(str(p) for p in (on_disk - claimed))
    assert not unclaimed, (
        f"unregistered forecast population(s) on disk: {unclaimed}. "
        f"Every ledger must be declared in forecast_populations._POPULATIONS "
        f"or it will be invisible to health exactly as the arena's was.")
