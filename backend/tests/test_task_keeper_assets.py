"""`task_keeper assets` (2026-10-07 chunk): bump the public-assets pin, gate the bump on
`test_public_assets.py`, then commit + push ONLY the rendered set -- same H1 guards as
`publish_commit`. Every step is injectable so no test shells out, touches git or imports the
real `render_public_assets` module's live globals."""
from __future__ import annotations

import subprocess
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
    assert set(captured["paths"]) == set(TK._asset_paths("2026-02-02T000000Z"))
    assert "docs/assets" not in captured["paths"]
    assert all(p != "docs/assets/README.md" for p in captured["paths"])
    assert captured["paths"][-1] == (
        "backend/data/optimus/paper_accounts/public_assets_refresh_2026-02-02T000000Z.json")
    assert "2026-02-02T000000Z" in captured["message"]
    assert captured["log_path"] != tmp_path / "assets.jsonl"   # the commit gets its OWN receipt stream
    assert out["commit"]["status"] == "COMMITTED" and out["commit"]["pushed"] is True


def test_asset_allowlist_does_not_stage_an_unrelated_local_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for rel in TK.ASSETS_COMMIT_PATHS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("updated\n", encoding="utf-8")
    unrelated = repo / "docs/assets/local_notes.txt"
    unrelated.write_text("private local note\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", *TK.ASSETS_COMMIT_PATHS], cwd=repo, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repo,
                            check=True, capture_output=True, text=True).stdout.splitlines()
    assert set(staged) == set(TK.ASSETS_COMMIT_PATHS)
    assert "docs/assets/local_notes.txt" not in staged


def test_push_retry_rejects_foreign_commit_hidden_by_its_revert(tmp_path, monkeypatch):
    repo = tmp_path / "aegis-finance-publication"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for key, val in (("user.name", "Asset Test"), ("user.email", "asset-test@example.invalid")):
        subprocess.run(["git", "config", key, val], cwd=repo, check=True)
    baseline = repo / "baseline.txt"
    baseline.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "baseline.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base], cwd=repo, check=True)
    foreign = repo / "foreign.txt"
    foreign.write_text("foreign\n", encoding="utf-8")
    subprocess.run(["git", "add", "foreign.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "foreign"], cwd=repo, check=True)
    foreign.unlink()
    subprocess.run(["git", "add", "foreign.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "revert foreign"], cwd=repo, check=True)
    asset = repo / "README.md"
    asset.write_text("assets\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "public assets refresh 2026-01-02T000000Z"],
                   cwd=repo, check=True)
    monkeypatch.setattr(TK, "REPO", repo)
    assert not TK._assets_unpushed_history_scoped("2026-01-02T000000Z")


def test_real_asset_caller_refuses_dirty_readme_then_retries_failed_test(
        tmp_path, monkeypatch):
    """Exercise the actual bump and Git commit on an isolated main checkout."""
    import shutil
    from scripts import render_public_assets as RPA
    from backend.services import publish_receipts as PR

    repo = tmp_path / "aegis-finance-publication"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "config", "user.name", "Asset Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "asset-test@example.invalid"], cwd=repo, check=True)
    script = repo / "scripts/render_public_assets.py"
    script.parent.mkdir()
    shutil.copy(RPA.__file__, script)
    readme = repo / "README.md"
    shutil.copy(RPA.README, readme)
    subprocess.run(["git", "add", "--", "scripts/render_public_assets.py", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)

    paper = tmp_path / "runtime_paper"
    paper.mkdir()
    for day in ("01", "02"):
        run_id = f"2026-01-{day}T000000Z"
        rows = [{"account": f"acct_{i}", "family": fam, "status": "LIVE", "roi_pct": 5.0 + i,
                 "spy_same_window_pct": 1.0, "vs_spy_pp": 4.0 + i, "start_capital": 100_000.0,
                 "inception": "2026-01-01", "book_id": None}
                for i, (fam, _) in enumerate(RPA.FEATURED_FAMILIES)]
        (paper / f"roi_{run_id}.json").write_text(
            __import__("json").dumps({"generated_utc": f"2026-01-{day}T00:00:00+00:00", "rows": rows}),
            encoding="utf-8")
        (paper / f"book_dna_{run_id}.json").write_text(
            __import__("json").dumps({"books": [{"account": f"acct_{i}", "sessions_graded": 1,
                                                  "evidence": {"label": "OBSERVED(1)"}, "tickers": []}
                                                 for i in range(3)]}), encoding="utf-8")
    source = script.read_text(encoding="utf-8")
    script.write_text(RPA.PIN_RE.sub('RESULTS_RUN_ID = "2026-01-01T000000Z"', source), encoding="utf-8")
    subprocess.run(["git", "add", "--", "scripts/render_public_assets.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "pin baseline"], cwd=repo, check=True)
    monkeypatch.setenv("AEGIS_PUBLICATION_ROOT", str(repo))
    monkeypatch.setattr(TK, "REPO", repo)
    monkeypatch.setattr(TK, "ASSETS_PENDING", tmp_path / "assets_pending.json")
    monkeypatch.setattr(RPA, "REPO", repo)
    monkeypatch.setattr(RPA, "__file__", str(script))
    monkeypatch.setattr(RPA, "README", readme)
    monkeypatch.setattr(RPA, "PAPER_DIR", paper)
    monkeypatch.setattr(RPA, "REFRESH_DIR", repo / "backend/data/optimus/paper_accounts")
    monkeypatch.setattr(RPA, "ASSETS", repo / "docs/assets")
    monkeypatch.setattr(RPA, "HERO_SVG", RPA.ASSETS / "aegis_loop.svg")
    monkeypatch.setattr(RPA, "RESULTS_SVG", RPA.ASSETS / "paper_results_live.svg")
    monkeypatch.setattr(RPA, "PIPELINE_SVG", RPA.ASSETS / "architecture_pipeline.svg")
    monkeypatch.setattr(RPA, "OG_SVG", RPA.ASSETS / "og_preview.svg")
    monkeypatch.setattr(RPA, "GAUNTLET_SVG", RPA.ASSETS / "gauntlet.svg")
    monkeypatch.setattr(RPA, "FRONT_HTML", repo / "docs/design/aegis_front_page.html")
    monkeypatch.setattr(RPA, "RESULTS_RUN_ID", "2026-01-01T000000Z")
    real_commit_paths = PR.commit_paths
    monkeypatch.setattr(PR, "commit_paths", lambda **kw: real_commit_paths(**kw, push=False))
    readme_before = readme.read_bytes()
    readme.write_text(readme.read_text(encoding="utf-8") + "\nUNRELATED OWNER DRAFT\n", encoding="utf-8")
    refused = TK.run_assets(pytest_runner=lambda *a, **kw: _Rc(0), log_path=tmp_path / "assets.jsonl")
    assert refused["action"] == "skip" and "owner edits" in refused["why"]
    assert RPA.RESULTS_RUN_ID == "2026-01-01T000000Z"
    readme.write_bytes(readme_before)
    script_before = script.read_bytes()
    script.write_bytes(script_before + b"\nunrelated_behavior_change = True\n")
    subprocess.run(["git", "add", "--", "scripts/render_public_assets.py"], cwd=repo, check=True)
    staged_refusal = TK.run_assets(pytest_runner=lambda *a, **kw: _Rc(0),
                                   log_path=tmp_path / "assets.jsonl")
    assert staged_refusal["action"] == "skip"
    assert b"unrelated_behavior_change" in script.read_bytes()
    subprocess.run(["git", "restore", "--staged", "--", "scripts/render_public_assets.py"],
                   cwd=repo, check=True)
    script.write_bytes(script_before)
    first = TK.run_assets(pytest_runner=lambda *a, **kw: _Rc(1, "failed"),
                          log_path=tmp_path / "assets.jsonl")
    assert first["action"] == "skip" and TK.ASSETS_PENDING.exists()
    assert RPA.RESULTS_RUN_ID == "2026-01-02T000000Z"
    generated_readme = readme.read_bytes()

    def passing_gate_with_owner_edit(*a, **kw):
        readme.write_bytes(readme.read_bytes() + b"\nUNRELATED EDIT DURING PYTEST\n")
        return _Rc(0, "passed")

    changed = TK.run_assets(pytest_runner=passing_gate_with_owner_edit,
                            log_path=tmp_path / "assets.jsonl")
    assert changed["action"] == "skip" and "changed after verification" in changed["why"]
    assert b"UNRELATED EDIT DURING PYTEST" in readme.read_bytes()
    readme.write_bytes(generated_readme)
    second = TK.run_assets(pytest_runner=lambda *a, **kw: _Rc(0, "passed"),
                           log_path=tmp_path / "assets.jsonl")
    assert second["action"] == "ok" and not TK.ASSETS_PENDING.exists()
    tracked = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo,
                             check=True, capture_output=True, text=True).stdout.splitlines()
    assert "docs/assets/public_results_2026-01-02T000000Z.json" in tracked
    assert "backend/data/optimus/paper_accounts/roi_2026-01-02T000000Z.json" not in tracked
    assert "UNRELATED OWNER DRAFT" not in readme.read_text(encoding="utf-8")


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
