"""The public-assets pin's age can go red, can go green, and an undateable pin is UNKNOWN
(2026-10-07 chunk). Mirrors `test_backtest_staleness.py`'s shape for the analogous probe.
Dates derived from `now`, never a literal calendar moment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def test_registered_in_system_health_and_runs_through_run_probes():
    assert any(p.name == "public_assets" for p in SH.PROBES)
    now = datetime.now(timezone.utc)
    # ctx.repo defaults to the real repo (ProbeCtx's own default), so this reads the real pin
    ctx = SH.ProbeCtx(optimus_dir=SH.REPO, now=now, allow_proc=False)
    rows = SH.run_probes(ctx, only={"public_assets"})
    assert len(rows) == 1
    assert rows[0]["verdict"] in ("ALIVE", "STALE", "UNKNOWN")
    assert rows[0]["proof"]


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
