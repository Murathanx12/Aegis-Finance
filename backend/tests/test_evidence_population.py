"""Two forward ledgers that can never be confused for one.

The ruling (docs/IIF1_PRE_NIGHT_1_CHECKLIST.md, FABLE ORDERS 2): the in-repo
~20,073-record ledger is the CAMPAIGN evidence population, resolved locally and
attended; the Railway volume's records are the LIVE production population. No
migration in either direction, no silent pooling, and the separation asserted in
code rather than remembered.

These tests are the code half. They run in BOTH topologies deliberately:

  * production, where the two ledgers are different files — the path check binds;
  * a developer machine, where AEGIS_DATA_DIR is unset and the two paths are the
    SAME FILE — the path check cannot bind, and the record field is the only
    thing standing between the two populations.

A separation that only holds in production is the wrong way round: the attended
campaign resolutions are run locally.
"""

from __future__ import annotations

import json

import pytest

from backend import config as _config
from backend.services import belief_state as BS
from backend.services import evidence_population as EP


@pytest.fixture
def split(tmp_path, monkeypatch):
    """Production topology: campaign in the image, live on the volume."""
    repo = tmp_path / "image" / "optimus"
    vol = tmp_path / "volume" / "optimus"
    repo.mkdir(parents=True)
    vol.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_LEGACY_DIR", repo)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", vol)
    return repo, vol


@pytest.fixture
def coincident(tmp_path, monkeypatch):
    """Developer topology: one directory, therefore one file."""
    one = tmp_path / "optimus"
    one.mkdir(parents=True)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_LEGACY_DIR", one)
    monkeypatch.setattr(_config, "OPTIMUS_LEDGER_DIR", one)
    return one


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8")


def _rec(pid: str, pop: str | None = None, **kw) -> dict:
    r = {"prediction_id": pid, "ticker": "AAPL", "made_at": "2026-08-11T00:00:00",
         "resolves_after": "2026-08-20", "observable": "abs_move_exceeds",
         "horizon_days": 5, "probability": 0.4, "outcome": None,
         "specialist": "s", "model": "m", "model_version": "v"}
    if pop:
        r["evidence_population"] = pop
    r.update(kw)
    return r


# ── the population must be named ────────────────────────────────────────────
def test_a_missing_population_refuses_rather_than_defaulting():
    with pytest.raises(EP.PopulationRequired):
        EP.parse(None)
    with pytest.raises(EP.PopulationRequired):
        EP.parse("")


def test_an_unknown_population_refuses():
    with pytest.raises(EP.PopulationRequired):
        EP.parse("the_forward_ledger")


def test_reading_requires_a_population(split):
    with pytest.raises(EP.PopulationRequired):
        EP.read_population(None)


# ── cross-writes ────────────────────────────────────────────────────────────
def test_campaign_cannot_write_the_live_ledger(split):
    _repo, vol = split
    with pytest.raises(EP.PopulationCrossWrite):
        EP.assert_write_allowed(EP.EvidencePopulation.CAMPAIGN_FORWARD,
                                vol / "predictions.jsonl")


def test_live_cannot_write_the_campaign_ledger(split):
    repo, _vol = split
    with pytest.raises(EP.PopulationCrossWrite):
        EP.assert_write_allowed(EP.EvidencePopulation.LIVE_FORWARD,
                                repo / "predictions.jsonl")


def test_sandbox_can_write_neither(split):
    repo, vol = split
    for target in (repo / "predictions.jsonl", vol / "predictions.jsonl"):
        with pytest.raises(EP.PopulationCrossWrite):
            EP.assert_write_allowed(EP.EvidencePopulation.SANDBOX, target)


def test_a_record_does_not_change_population(split):
    rows = [_rec("p1", "live_forward")]
    with pytest.raises(EP.PopulationCrossWrite):
        EP.stamp(rows, "campaign_forward")


# ── the coincident case: the field is the wall ──────────────────────────────
def test_where_the_paths_coincide_the_field_still_separates(coincident):
    """The developer machine. This is where the campaign resolutions run."""
    assert EP.paths_coincide()
    p = coincident / "predictions.jsonl"
    _write(p, [_rec("c1"), _rec("c2"), _rec("l1", "live_forward")])

    campaign = EP.read_population("campaign_forward")
    live = EP.read_population("live_forward")
    assert {r["prediction_id"] for r in campaign} == {"c1", "c2"}
    assert {r["prediction_id"] for r in live} == {"l1"}


def test_untagged_records_in_a_coincident_file_are_the_campaigns(coincident):
    """The file in the repo is the campaign's history; the volume is absent."""
    _write(coincident / "predictions.jsonl", [_rec("old1"), _rec("old2")])
    assert len(EP.read_population("campaign_forward")) == 2
    assert EP.read_population("live_forward") == []


def test_the_status_report_discloses_the_coincidence(coincident):
    _write(coincident / "predictions.jsonl", [_rec("c1")])
    st = EP.status()
    assert st["paths_coincide"] is True
    assert "SAME FILE" in st["coincidence_note"]
    assert st["populations"]["campaign_forward"]["raw_predictions"] == 1
    assert st["populations"]["live_forward"]["raw_predictions"] == 0


# ── the volume stays authoritative for LIVE ─────────────────────────────────
def test_the_volume_is_authoritative_for_live_forward(split):
    repo, vol = split
    _write(repo / "predictions.jsonl", [_rec(f"campaign{i}") for i in range(50)])
    _write(vol / "predictions.jsonl", [_rec(f"live{i}") for i in range(3)])

    live = EP.read_population("live_forward")
    assert len(live) == 3
    assert all(r["prediction_id"].startswith("live") for r in live)
    assert len(EP.read_population("campaign_forward")) == 50


def test_the_two_counts_are_never_summed(split):
    repo, vol = split
    _write(repo / "predictions.jsonl", [_rec("c1")])
    _write(vol / "predictions.jsonl", [_rec("l1")])
    st = EP.status()
    assert st["populations"]["campaign_forward"]["raw_predictions"] == 1
    assert st["populations"]["live_forward"]["raw_predictions"] == 1
    assert "REFUSED" in st["pooling"]
    assert "total" not in st                     # there is no combined number


def test_pooling_refuses(split):
    EP.refuse_pooling("campaign_forward", "campaign_forward")     # fine
    with pytest.raises(EP.PopulationPoolingRefused):
        EP.refuse_pooling("campaign_forward", "live_forward")


# ── ids may repeat across populations without colliding ─────────────────────
def test_the_same_prediction_id_in_both_populations_does_not_collide(split):
    repo, vol = split
    _write(repo / "predictions.jsonl", [_rec("SHARED-ID", ticker="AAPL")])
    _write(vol / "predictions.jsonl", [_rec("SHARED-ID", ticker="MSFT")])

    c = EP.read_population("campaign_forward")
    l = EP.read_population("live_forward")
    assert len(c) == len(l) == 1
    assert c[0]["ticker"] == "AAPL" and l[0]["ticker"] == "MSFT"
    # And their lineage says which ledger each came from.
    assert (EP.lineage("campaign_forward")["ledger_id"]
            != EP.lineage("live_forward")["ledger_id"])


# ── lineage on every write ──────────────────────────────────────────────────
def test_lineage_carries_everything_a_verdict_must_state(split):
    repo, _vol = split
    _write(repo / "predictions.jsonl", [_rec("c1"), _rec("c2")])
    lin = EP.lineage("campaign_forward")
    for key in ("evidence_population", "ledger_id", "logical_uri",
                "ledger_path", "record_count", "first_record_at",
                "last_record_at", "provenance_sha256", "source_commit",
                "resolver", "paths_coincide"):
        assert key in lin, key
    assert lin["record_count"] == 2
    assert lin["first_record_at"] == "2026-08-11T00:00:00"


def test_appended_records_are_stamped_with_their_ledgers_population(split,
                                                                   monkeypatch):
    repo, _vol = split
    from backend.services.belief_state import Observable, make_prediction
    rec = make_prediction(
        ticker="AAPL", specialist="s", observable=Observable.ABS_MOVE_EXCEEDS,
        horizon_days=5, probability=0.4, threshold=0.05, thesis="t",
        counter_thesis="c", next_observable="n", model="m", model_version="v",
        prompt="p", input_snapshot={"a": 1})
    assert rec.evidence_population is None          # not decided at build time

    BS.append([rec], repo / "predictions.jsonl")
    written = json.loads((repo / "predictions.jsonl").read_text(
        encoding="utf-8").strip())
    assert written["evidence_population"] == "campaign_forward"
    assert written["ledger_id"] == "aegis:ledger:campaign_forward"


def test_append_refuses_an_explicit_population_it_cannot_honour(split):
    repo, _vol = split
    from backend.services.belief_state import Observable, make_prediction
    rec = make_prediction(
        ticker="AAPL", specialist="s", observable=Observable.ABS_MOVE_EXCEEDS,
        horizon_days=5, probability=0.4, threshold=0.05, thesis="t",
        counter_thesis="c", next_observable="n", model="m", model_version="v",
        prompt="p", input_snapshot={"a": 1})
    with pytest.raises(EP.PopulationCrossWrite):
        BS.append([rec], repo / "predictions.jsonl", population="live_forward")


def test_a_tmp_path_write_is_unattributed_rather_than_mislabelled(tmp_path):
    """A test ledger is not one of the declared populations, and saying it is
    would put a fabricated lineage on a fabricated record."""
    from backend.services.belief_state import Observable, make_prediction
    rec = make_prediction(
        ticker="AAPL", specialist="s", observable=Observable.ABS_MOVE_EXCEEDS,
        horizon_days=5, probability=0.4, threshold=0.05, thesis="t",
        counter_thesis="c", next_observable="n", model="m", model_version="v",
        prompt="p", input_snapshot={"a": 1})
    BS.append([rec], tmp_path / "some.jsonl")
    row = json.loads((tmp_path / "some.jsonl").read_text(encoding="utf-8").strip())
    assert row["evidence_population"] is None


# ── the resolvers ───────────────────────────────────────────────────────────
def test_the_resolver_refuses_a_mixed_ledger(coincident):
    """Resolution rewrites the whole file, so a mixed file grades both."""
    from backend.services.ledger_resolver import assert_single_population
    p = coincident / "predictions.jsonl"
    _write(p, [_rec("c1"), _rec("l1", "live_forward")])
    with pytest.raises(EP.PopulationCrossWrite):
        assert_single_population(p, "campaign_forward")


def test_the_resolver_accepts_a_single_population_ledger(coincident):
    from backend.services.ledger_resolver import assert_single_population
    p = coincident / "predictions.jsonl"
    _write(p, [_rec("c1"), _rec("c2", "campaign_forward")])
    found = assert_single_population(p, "campaign_forward")
    assert found == {"campaign_forward": 2}


def test_the_production_resolver_cannot_be_pointed_at_the_campaign_ledger(split):
    from backend.services.ledger_resolver import resolve_due
    repo, _vol = split
    _write(repo / "predictions.jsonl", [_rec("c1")])
    with pytest.raises(EP.PopulationCrossWrite):
        resolve_due(repo / "predictions.jsonl", population="live_forward")


def test_a_resolver_run_reports_its_lineage(split):
    from backend.services.ledger_resolver import resolve_due
    _repo, vol = split
    _write(vol / "predictions.jsonl",
           [_rec("l1", resolves_after="2099-01-01")])
    report = resolve_due(population="live_forward")
    assert report["lineage"]["evidence_population"] == "live_forward"
    assert report["lineage"]["record_count"] == 1


def test_the_production_job_names_its_population():
    """Pinned in the source: the job must not inherit a default."""
    import inspect
    from backend.services.portfolio_intelligence import scheduler
    src = inspect.getsource(scheduler._ledger_resolve)
    assert 'population="live_forward"' in src


# ── the existing history still reads ────────────────────────────────────────
def test_old_records_without_the_field_remain_readable_and_reproducible(split):
    """20k records written before this existed must not become unreadable."""
    repo, _vol = split
    rows = [_rec(f"old{i}") for i in range(20)]
    for r in rows:
        r.pop("evidence_population", None)
    _write(repo / "predictions.jsonl", rows)

    got = EP.read_population("campaign_forward")
    assert len(got) == 20
    assert all("evidence_population" not in r for r in got)   # unmodified
    assert EP.lineage("campaign_forward")["record_count"] == 20
