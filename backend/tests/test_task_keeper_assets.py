"""`task_keeper assets` (2026-10-07 chunk): bump the public-assets pin, gate the bump on
`test_public_assets.py`, then commit + push ONLY the rendered set -- same H1 guards as
`publish_commit`. Every step is injectable so no test shells out, touches git or imports the
real `render_public_assets` module's live globals."""
from __future__ import annotations

from pathlib import Path

from scripts import task_keeper as TK


class _Rc:
    def __init__(self, returncode: int = 0, stdout: str = ""):
        self.returncode = returncode
        self.stdout = stdout


def test_a_refused_bump_is_a_skip_and_nothing_else_runs(tmp_path):
    calls = {"pytest": 0, "commit": 0}

    def bump():
        return 2

    def pytest_runner(*a, **kw):
        calls["pytest"] += 1
        return _Rc(0)

    def commit(**kw):
        calls["commit"] += 1
        return {"status": "COMMITTED", "pushed": True}

    out = TK.run_assets(bump=bump, pytest_runner=pytest_runner, commit=commit,
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip"
    assert "refused" in out["why"]
    assert calls == {"pytest": 0, "commit": 0}


def test_a_bump_exit_code_other_than_0_or_2_is_a_skip(tmp_path):
    calls = {"pytest": 0}

    def bump():
        return 1

    def pytest_runner(*a, **kw):
        calls["pytest"] += 1
        return _Rc(0)

    out = TK.run_assets(bump=bump, pytest_runner=pytest_runner, commit=lambda **kw: {},
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip" and "exited 1" in out["why"]
    assert calls["pytest"] == 0


def test_a_bump_that_raises_is_a_skip_never_a_raise(tmp_path):
    def bump():
        raise RuntimeError("boom")

    out = TK.run_assets(bump=bump, pytest_runner=lambda *a, **kw: _Rc(0), commit=lambda **kw: {},
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip"
    assert "boom" in out["why"]


def test_a_failed_pinning_test_is_a_skip_and_the_commit_never_runs(tmp_path):
    calls = {"commit": 0}

    def bump():
        return 0

    def pytest_runner(*a, **kw):
        return _Rc(1, "FAILED backend/tests/test_public_assets.py::test_x - AssertionError\n1 failed")

    def commit(**kw):
        calls["commit"] += 1
        return {"status": "COMMITTED", "pushed": True}

    out = TK.run_assets(bump=bump, pytest_runner=pytest_runner, commit=commit,
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip"
    assert "test_public_assets.py failed" in out["why"]
    assert calls["commit"] == 0
    assert out["pytest_rc"] == 1


def test_a_pytest_runner_that_raises_is_a_skip(tmp_path):
    def pytest_runner(*a, **kw):
        raise OSError("no such file")

    out = TK.run_assets(bump=lambda: 0, pytest_runner=pytest_runner, commit=lambda **kw: {},
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip" and "no such file" in out["why"]


def test_a_commit_that_is_not_committed_or_not_pushed_is_a_skip(tmp_path):
    out_not_committed = TK.run_assets(
        bump=lambda: 0, pytest_runner=lambda *a, **kw: _Rc(0),
        commit=lambda **kw: {"status": "REFUSED", "reasons": ["staged change outside the folder"]},
        log_path=tmp_path / "assets.jsonl")
    assert out_not_committed["action"] == "skip"
    assert out_not_committed["why"] == ["staged change outside the folder"]

    out_not_pushed = TK.run_assets(
        bump=lambda: 0, pytest_runner=lambda *a, **kw: _Rc(0),
        commit=lambda **kw: {"status": "COMMITTED", "pushed": False, "push_refused": "non-fast-forward"},
        log_path=tmp_path / "assets.jsonl")
    assert out_not_pushed["action"] == "skip"
    assert out_not_pushed["why"] == "non-fast-forward"


def test_a_commit_that_raises_is_a_skip(tmp_path):
    def commit(**kw):
        raise RuntimeError("git not found")

    out = TK.run_assets(bump=lambda: 0, pytest_runner=lambda *a, **kw: _Rc(0), commit=commit,
                        log_path=tmp_path / "assets.jsonl")
    assert out["action"] == "skip" and "git not found" in out["why"]


def test_the_successful_path_commits_exactly_the_declared_paths_plus_the_receipt(tmp_path):
    captured = {}

    def bump():
        from scripts import render_public_assets as RPA
        RPA.RESULTS_RUN_ID = "2026-02-02T000000Z"
        return 0

    def pytest_runner(*a, **kw):
        return _Rc(0, "5 passed")

    def commit(**kw):
        captured.update(kw)
        return {"status": "COMMITTED", "commit": "abc123", "pushed": True, "n_files": 7}

    from scripts import render_public_assets as RPA
    old_id = RPA.RESULTS_RUN_ID
    try:
        out = TK.run_assets(bump=bump, pytest_runner=pytest_runner, commit=commit,
                            log_path=tmp_path / "assets.jsonl")
    finally:
        RPA.RESULTS_RUN_ID = old_id

    assert out["action"] == "ok"
    assert out["old_run_id"] != "2026-02-02T000000Z"
    assert out["new_run_id"] == "2026-02-02T000000Z"
    assert set(TK.ASSETS_COMMIT_PATHS) <= set(captured["paths"])
    assert captured["paths"][-1] == (
        "backend/data/optimus/paper_accounts/public_assets_refresh_2026-02-02T000000Z.json")
    assert "2026-02-02T000000Z" in captured["message"]
    assert captured["log_path"] != tmp_path / "assets.jsonl"   # the commit gets its OWN receipt stream
    assert out["commit"]["status"] == "COMMITTED" and out["commit"]["pushed"] is True


def test_results_voice_is_named_only_when_the_file_exists(tmp_path):
    from scripts import render_public_assets as RPA
    old_id = RPA.RESULTS_RUN_ID
    voice_p = RPA.PAPER_DIR / f"results_voice_{old_id}.md"
    made = not voice_p.is_file()
    if made:
        voice_p.write_text("# voice\n", encoding="utf-8")
    try:
        out = TK.run_assets(bump=lambda: 0, pytest_runner=lambda *a, **kw: _Rc(0, "ok"),
                            commit=lambda **kw: {"status": "COMMITTED", "pushed": True},
                            log_path=tmp_path / "assets.jsonl")
        assert out["results_voice"] == f"backend/data/optimus/paper_accounts/results_voice_{old_id}.md"
    finally:
        if made:
            voice_p.unlink()


def test_no_results_voice_key_when_the_file_is_absent(tmp_path):
    """A fake run id that provably has no `results_voice_<id>.md` -- never relies on
    whatever happens to be committed for the real pin, which a later chunk may add."""
    from scripts import render_public_assets as RPA
    fake_id = "1999-01-01T000000Z"
    voice_p = RPA.PAPER_DIR / f"results_voice_{fake_id}.md"
    assert not voice_p.is_file()

    def bump():
        RPA.RESULTS_RUN_ID = fake_id
        return 0

    old_id = RPA.RESULTS_RUN_ID
    try:
        out = TK.run_assets(bump=bump, pytest_runner=lambda *a, **kw: _Rc(0, "ok"),
                            commit=lambda **kw: {"status": "COMMITTED", "pushed": True},
                            log_path=tmp_path / "assets.jsonl")
    finally:
        RPA.RESULTS_RUN_ID = old_id
    assert "results_voice" not in out


def test_assets_is_a_valid_job_and_wired_into_main(tmp_path, monkeypatch):
    monkeypatch.setattr(TK, "run_assets", lambda: {"action": "skip", "why": "stub"})
    rc = TK.main(["assets"])
    assert rc == 2


def test_assets_ok_job_exits_zero(monkeypatch):
    monkeypatch.setattr(TK, "run_assets", lambda: {"action": "ok"})
    rc = TK.main(["assets"])
    assert rc == 0


def test_the_weekly_task_is_named_in_register_but_this_test_never_registers_it():
    ps = TK.registration_ps()
    assert TK.TASK_ASSETS in ps
    assert "AegisPublicAssetsWeekly" in ps
    assert "-Weekly" in ps and "scripts.task_keeper assets" in ps


def test_the_weekly_trigger_reads_its_day_and_time_from_config(monkeypatch):
    from backend import config as C
    monkeypatch.setattr(C, "PUBLIC_ASSETS_REFRESH_WEEKDAY", 0)      # Monday
    monkeypatch.setattr(C, "PUBLIC_ASSETS_REFRESH_HHMM", "1234")
    assert TK._assets_day_name() == "Monday"
    assert TK._assets_hhmm_colon() == "12:34"
