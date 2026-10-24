"""The public-assets pin's age can go red, can go green, and an undateable pin is UNKNOWN
(2026-10-07 chunk). Mirrors `test_backtest_staleness.py`'s shape for the analogous probe.
Dates derived from `now`, never a literal calendar moment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import config as C
from backend.services import public_assets_staleness as PAS
from backend.services import system_health as SH


def test_a_fresh_pin_is_alive():
    now = datetime.now(timezone.utc)
    rid = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H%M%SZ")
    r = PAS.pin_age(now, run_id=rid, stale_days=10)
    assert r["verdict"] == "ALIVE" and 80000 < r["age_s"] < 90000


def test_an_old_pin_goes_stale_and_names_the_remedy():
    now = datetime.now(timezone.utc)
    rid = (now - timedelta(days=40)).strftime("%Y-%m-%dT%H%M%SZ")
    r = PAS.pin_age(now, run_id=rid, stale_days=10)
    assert r["verdict"] == "STALE" and "bump-pin" in r["detail"]


def test_an_unreadable_or_undateable_pin_is_unknown(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(PAS, "pinned_run_id", lambda repo=None: None)
    assert PAS.pin_age(now)["verdict"] == "UNKNOWN"            # run_id=None -> read the (absent) real pin
    assert PAS.pin_age(now, run_id="")["verdict"] == "UNKNOWN"
    assert PAS.pin_age(now, run_id="not-a-timestamp")["verdict"] == "UNKNOWN"
    assert PAS.pin_age(now, run_id="2026-13-45T999999Z")["verdict"] == "UNKNOWN"


def test_an_empty_repo_has_no_evidence(tmp_path):
    """A `ctx.repo` with no `scripts/render_public_assets.py` (the generic
    `test_every_probe_with_its_evidence_absent_is_not_alive` shape) is UNKNOWN, never ALIVE."""
    now = datetime.now(timezone.utc)
    assert PAS.pin_script_text(tmp_path) is None
    assert PAS.pinned_run_id(tmp_path) is None
    assert PAS.pin_age(now, repo=tmp_path)["verdict"] == "UNKNOWN"


def test_pinned_run_id_reads_a_given_repos_copy_of_the_script(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "render_public_assets.py").write_text(
        'x = 1\nRESULTS_RUN_ID = "2026-03-04T050607Z"\ny = 2\n', encoding="utf-8")
    assert PAS.pinned_run_id(tmp_path) == "2026-03-04T050607Z"


def test_the_threshold_comes_from_config():
    now = datetime.now(timezone.utc)
    rid = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H%M%SZ")
    assert PAS._threshold_days() == float(C.PUBLIC_ASSETS_MAX_PIN_AGE_DAYS)
    # stale_days=None falls back to the config value
    r1 = PAS.pin_age(now, run_id=rid)
    r2 = PAS.pin_age(now, run_id=rid, stale_days=C.PUBLIC_ASSETS_MAX_PIN_AGE_DAYS)
    assert r1 == r2


def test_pinned_run_id_reads_the_real_committed_file():
    from scripts import render_public_assets as RPA
    assert PAS.pinned_run_id() == RPA.RESULTS_RUN_ID


@pytest.mark.parametrize("age_days,verdict,state,light", [
    (1, "ALIVE", "ALIVE", "GREEN"),
    (40, "STALE", "DEGRADED", "RED"),
    (None, "UNKNOWN", "UNKNOWN", "AMBER"),
])
def test_registered_in_system_health_and_runs_through_run_probes(
        tmp_path, monkeypatch, age_days, verdict, state, light):
    assert any(p.name == "public_assets" for p in SH.PROBES)
    # Select the local probe route explicitly, independent of the host/CI env.
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.setattr(C, "PUBLIC_ASSETS_MAX_PIN_AGE_DAYS", 10)
    now = datetime(2026, 10, 24, 18, tzinfo=timezone.utc)
    if age_days is not None:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        rid = (now - timedelta(days=age_days)).strftime("%Y-%m-%dT%H%M%SZ")
        (scripts / "render_public_assets.py").write_text(
            f'RESULTS_RUN_ID = "{rid}"\n', encoding="utf-8")
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, repo=tmp_path, now=now, allow_proc=False)
    private = PAS.p_public_assets(ctx)
    assert private.verdict == verdict and private.proof
    rows = SH.run_probes(ctx, only={"public_assets"})
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == row["probe"] == "public_assets"
    assert row["verdict"] == verdict and row["state"] == state
    assert row["evidence_utc"] == private.evidence_utc
    assert row["age_s"] == private.age_s
    assert row["alarm"]["light"] == light
    assert row["alarm"]["healthy"] == (light == "GREEN")
    assert row["alarm"]["attention_required"] == (light != "GREEN")
    if light == "GREEN":
        assert row["proof"] == private.proof
    else:
        # A stale/unknown public row withholds freeform proof, without hiding
        # the failure verdict, structured clocks or alarm.
        assert row["public_view"] == SH.PUBLIC_FAILURE_VIEW
        assert row["proof"] == ""


def test_an_empty_ctx_repo_reports_unknown_not_alive(tmp_path):
    """The exact shape `test_system_health.test_every_probe_with_its_evidence_absent_is_not_alive`
    exercises for every registered probe: an empty `ctx.repo` must never be ALIVE."""
    now = datetime.now(timezone.utc)
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=now, repo=tmp_path, allow_proc=False)
    rows = SH.run_probes(ctx, only={"public_assets"})
    assert rows[0]["verdict"] == "UNKNOWN"


def test_p_public_assets_state_is_degraded_exactly_when_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    fresh_rid = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H%M%SZ")
    stale_rid = (now - timedelta(days=40)).strftime("%Y-%m-%dT%H%M%SZ")

    class Ctx:
        pass
    ctx = Ctx()
    ctx.now = now

    monkeypatch.setattr(PAS, "pinned_run_id", lambda repo=None: fresh_rid)
    fresh = PAS.p_public_assets(ctx)
    assert fresh.verdict == "ALIVE" and fresh.state in (None, "ALIVE")

    monkeypatch.setattr(PAS, "pinned_run_id", lambda repo=None: stale_rid)
    stale = PAS.p_public_assets(ctx)
    assert stale.verdict == "STALE" and stale.state == "DEGRADED"
