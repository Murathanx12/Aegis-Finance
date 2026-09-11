"""The thin launcher (roadmap O1): each step is a pure function with a receipt.

WHAT THESE TESTS ARE ACTUALLY FOR. The launcher's job is to make the .exe run
the code you read, which retires a defect FAMILY -- six instances by 2026-09-11
of "a path that resolves differently when frozen". The risk it introduces in
exchange is a different one: an update step that does something surprising to a
working checkout. So the tests below care most about the REFUSALS and the
SKIPS -- a dirty tree is never pulled, a failed pull is never fatal, pip does not
run when the hash is unchanged, a missing Node serves the last export -- and
about the receipt saying, for every step, whether it ran and why not.

Every subprocess is faked. A test that actually pulled would be a test that
depends on the network, on a remote, and on what somebody pushed.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from desktop import _interp, launcher

REPO = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------ the interpreter

def test_from_source_the_interpreter_is_this_one():
    interp, why = _interp.resolve(REPO, frozen=False)
    assert interp == sys.executable
    assert "source" in why


def test_frozen_prefers_the_env_var(tmp_path, monkeypatch):
    fake = tmp_path / "python.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("AEGIS_JOB_PYTHON", str(fake))
    interp, why = _interp.resolve(tmp_path, frozen=True)
    assert interp == str(fake)
    assert why == "AEGIS_JOB_PYTHON"


def test_frozen_falls_back_to_the_checkouts_venv(tmp_path, monkeypatch):
    monkeypatch.delenv("AEGIS_JOB_PYTHON", raising=False)
    venv = tmp_path / ".venv" / "Scripts"
    venv.mkdir(parents=True)
    (venv / "python.exe").write_text("", encoding="utf-8")
    interp, why = _interp.resolve(tmp_path, frozen=True)
    assert interp == str(venv / "python.exe")
    assert ".venv" in why


def test_a_named_but_absent_interpreter_is_reported_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_JOB_PYTHON", str(tmp_path / "nope.exe"))
    _, why = _interp.resolve(tmp_path, frozen=True)
    assert "does not exist" in why


def test_the_control_router_uses_the_same_resolver_rather_than_its_own_copy():
    """Two copies of a resolution order drift the moment one learns a new venv
    layout. Read the AST so a docstring mentioning `_interp` cannot satisfy it."""
    src = (REPO / "backend" / "routers" / "control.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "job_python")
    imported = {a.name for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)
                for a in n.names}
    assert "resolve" in imported, "job_python no longer imports desktop._interp.resolve"


# ------------------------------------------------------- step 1: the checkout

@pytest.fixture(autouse=True)
def _no_real_pointer_file(tmp_path_factory, monkeypatch):
    """The pointer file is the LAST resort of `find_checkout`, and on this
    machine it exists and points at the real repository -- so without this every
    "no checkout found" test passes by finding the actual checkout."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("localappdata")))
    monkeypatch.delenv("AEGIS_REPO_ROOT", raising=False)


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for m in launcher.MARKERS:
        (root / m).mkdir(parents=True, exist_ok=True)
    return root


def test_the_env_var_wins_when_it_points_at_a_checkout(tmp_path):
    root = _checkout(tmp_path)
    found = launcher.find_checkout({"AEGIS_REPO_ROOT": str(root)}, frozen=True)
    assert found["ok"] and Path(found["root"]) == root
    assert found["how"] == "AEGIS_REPO_ROOT"


def test_the_exes_parents_are_searched_when_the_env_var_is_absent(tmp_path):
    root = _checkout(tmp_path)
    exe = root / "dist_next" / "AegisDesktop" / "AegisDesktop.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    found = launcher.find_checkout({}, exe=exe, frozen=True)
    assert Path(found["root"]) == root
    assert found["how"] == "a parent of the .exe"


def test_a_directory_missing_one_marker_is_not_a_checkout(tmp_path):
    root = _checkout(tmp_path)
    (root / ".git").rmdir()
    found = launcher.find_checkout({"AEGIS_REPO_ROOT": str(root)},
                                   exe=tmp_path / "x.exe", frozen=True)
    assert not found["ok"]
    # A refusal that does not say what it looked for sends the reader to the
    # source; this one lists every candidate and the markers it wanted.
    assert found["markers"] == list(launcher.MARKERS)
    assert any(str(root) in x for x in found["looked_in"])


def test_the_refusal_names_every_place_it_looked(tmp_path):
    found = launcher.find_checkout({}, exe=tmp_path / "deep" / "x.exe", frozen=True)
    assert not found["ok"]
    assert len(found["looked_in"]) >= 2


# --------------------------------------------------------------- step 2: git

class _FakeRun:
    """Replaces `subprocess.run` with a scripted answer per command."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        for key, (rc, out, err) in self.answers.items():
            if key in " ".join(cmd):
                return subprocess.CompletedProcess(cmd, rc, out, err)
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_a_dirty_tree_is_never_pulled(tmp_path, monkeypatch):
    fake = _FakeRun({"status --porcelain": (0, " M backend/main.py\n", ""),
                     "rev-parse": (0, "abc123\n", "")})
    monkeypatch.setattr(launcher.subprocess, "run", fake)
    step = launcher.update_checkout(tmp_path)
    assert step["updated"] is False
    assert step["reason"] == "local changes present"
    assert step["dirty"] is True
    assert step["dirty_files"] == [" M backend/main.py"]
    assert not any("pull" in " ".join(c) for c in fake.calls), (
        "an update mechanism that touches a dirty tree is worse than one that "
        "does nothing")


def test_a_clean_tree_pulls_and_records_both_heads(tmp_path, monkeypatch):
    heads = iter(["old111\n", "new222\n"])

    class _F(_FakeRun):
        def __call__(self, cmd, **kw):
            self.calls.append(list(cmd))
            joined = " ".join(cmd)
            if "rev-parse" in joined:
                return subprocess.CompletedProcess(cmd, 0, next(heads), "")
            if "status --porcelain" in joined:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "Fast-forward\n", "")

    monkeypatch.setattr(launcher.subprocess, "run", _F({}))
    step = launcher.update_checkout(tmp_path)
    assert step["head_before"] == "old111"
    assert step["head_after"] == "new222"
    assert step["updated"] is True and step["reason"] == "pulled"


def test_a_failed_pull_is_recorded_and_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({
        "status --porcelain": (0, "", ""),
        "rev-parse": (0, "abc\n", ""),
        "pull": (1, "", "fatal: could not read from remote\n"),
    }))
    step = launcher.update_checkout(tmp_path)
    assert step["updated"] is False
    assert "pull" in step["reason"] and "failed" in step["reason"]
    assert step["pull"]["returncode"] == 1


def test_no_head_moved_is_up_to_date_not_updated(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({
        "status --porcelain": (0, "", ""),
        "rev-parse": (0, "same\n", ""),
        "pull": (0, "Already up to date.\n", ""),
    }))
    step = launcher.update_checkout(tmp_path)
    assert step["updated"] is False and step["reason"] == "already up to date"


# --------------------------------------------------------------- step 3: pip

def test_pip_does_not_run_when_the_requirements_hash_is_unchanged(tmp_path, monkeypatch):
    req = tmp_path / "requirements.txt"
    req.write_text("fastapi==1\n", encoding="utf-8")
    sha = launcher._sha256_file(req)
    fake = _FakeRun({})
    monkeypatch.setattr(launcher.subprocess, "run", fake)
    step = launcher.maybe_pip(tmp_path, "python", {"sha256": sha})
    assert step["ran"] is False
    assert "unchanged" in step["reason"]
    assert fake.calls == []


def test_pip_runs_when_the_hash_moved(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("fastapi==2\n", encoding="utf-8")
    fake = _FakeRun({"pip": (0, "Successfully installed\n", "")})
    monkeypatch.setattr(launcher.subprocess, "run", fake)
    step = launcher.maybe_pip(tmp_path, "python", {"sha256": "something else"})
    assert step["ran"] is True and step["returncode"] == 0
    assert any("pip" in " ".join(c) for c in fake.calls)


def test_a_failed_pip_says_the_app_still_starts(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("nope\n", encoding="utf-8")
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({"pip": (1, "", "boom")}))
    step = launcher.maybe_pip(tmp_path, "python", {})
    assert step["ran"] is True and "still starts" in step["reason"]


def test_no_requirements_file_is_a_named_skip(tmp_path):
    step = launcher.maybe_pip(tmp_path, "python", {})
    assert step["ran"] is False and "requirements.txt" in step["reason"]


# ---------------------------------------------------------- step 4: frontend

def test_the_frontend_is_not_rebuilt_when_nothing_changed(tmp_path, monkeypatch):
    (tmp_path / "frontend" / "out").mkdir(parents=True)
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({
        "rev-parse": (0, "head1\n", ""),
        "diff --quiet": (0, "", ""),
    }))
    step = launcher.maybe_frontend(tmp_path, {"export_head": "old"})
    assert step["ran"] is False
    assert "unchanged" in step["reason"]


def test_a_missing_export_is_rebuilt_even_when_nothing_changed(tmp_path, monkeypatch):
    """`frontend/out` absent is not "unchanged", it is "there is nothing to
    serve" -- a window showing the API's raw JSON is the failure that looks
    like a crash and is not."""
    import shutil
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({
        "rev-parse": (0, "head1\n", ""), "diff --quiet": (0, "", "")}))
    monkeypatch.setattr(shutil, "which", lambda _n: "npx")
    calls = []

    def _build(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "Export successful", "")

    monkeypatch.setattr(launcher.subprocess, "run", _build)
    step = launcher.maybe_frontend(tmp_path, {"export_head": "head1"})
    assert step["ran"] is True
    assert any(c[-2:] == ["next", "build"] for c in calls), calls


def test_node_absent_serves_the_last_export_rather_than_refusing(tmp_path, monkeypatch):
    import shutil
    (tmp_path / "frontend" / "out").mkdir(parents=True)
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({
        "rev-parse": (0, "head2\n", ""), "diff --quiet": (1, "", "")}))
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    step = launcher.maybe_frontend(tmp_path, {"export_head": "head1"})
    assert step["ran"] is False and "Node" in step["reason"]


def test_no_recorded_export_head_counts_as_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", _FakeRun({}))
    changed, why = launcher.frontend_changed(tmp_path, None)
    assert changed and "no recorded export head" in why


# ------------------------------------------------------------ step 5: the child

def test_the_shell_is_started_from_the_checkout_by_module():
    argv = launcher.shell_argv("C:/py/python.exe", "/desktop")
    assert argv[:4] == ["C:/py/python.exe", "-m", "desktop.aegis_desktop", "--page"]


def test_the_launcher_never_imports_backend():
    """The whole point. Anything the launcher imports is FROZEN with it, and
    anything frozen can resolve a path differently from the checkout."""
    src = (REPO / "desktop" / "launcher.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            names.add(n.module.split(".")[0])
    assert "backend" not in names, f"launcher imports backend: {sorted(names)}"
    assert "scripts" not in names and "learner" not in names
    # `desktop.aegis_desktop` is named as a STRING in `shell_argv` and nowhere
    # imported. Read the AST: the module name appears in this file's own
    # docstring too, and a grep-shaped guard that cannot tell an explanation
    # from an instance is a broken guard (protocol §10).
    imported_full = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported_full |= {al.name for al in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported_full.add(n.module)
    assert "desktop.aegis_desktop" not in imported_full


def test_interp_never_imports_backend_either():
    src = (REPO / "desktop" / "_interp.py").read_text(encoding="utf-8")
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            assert all(not a.name.startswith("backend") for a in n.names)
        if isinstance(n, ast.ImportFrom):
            assert not (n.module or "").startswith("backend")


def test_the_spec_freezes_the_launcher_and_excludes_the_app():
    spec = (REPO / "desktop" / "AegisDesktop.spec").read_text(encoding="utf-8")
    assert 'desktop" / "launcher.py' in spec
    for mod in ("backend", "scripts", "learner", "torch", "pandas"):
        assert f'"{mod}"' in spec.split("excludes = [", 1)[1].split("]", 1)[0], mod


# ------------------------------------------------------------------ the receipt

def test_every_step_including_the_skipped_ones_is_in_the_receipt(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    (root / "backend" / "data" / "optimus").mkdir(parents=True)
    monkeypatch.setenv("AEGIS_REPO_ROOT", str(root))
    monkeypatch.setattr(launcher, "remember_checkout",
                        lambda r: {"ok": True, "path": "fake"})

    class _Proc:
        pid = 4321

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(launcher, "spawn_shell", lambda r, argv: {
        "proc": _Proc(), "job_handle": None, "log": open(tmp_path / "l.txt", "w"),
        "record": {"step": "shell", "argv": argv, "pid": 4321,
                   "job_object": {"bound": False}, "bound": {"bound": False}}})

    code = launcher.main(["--no-update"])
    assert code == 0
    receipt = json.loads(launcher.receipt_path(root).read_text(encoding="utf-8"))
    steps = {s["step"]: s for s in receipt["steps"]}
    assert set(steps) >= {"find_checkout", "interpreter", "git", "pip",
                          "frontend", "shell"}
    for name in ("git", "pip", "frontend"):
        assert steps[name]["ran"] is False
        assert steps[name]["reason"] == "--no-update", (
            "a step that did nothing must say WHY it did nothing (invariant 15)")
    assert receipt["status"] == "OK"
    assert receipt["shell_returncode"] == 0


def test_a_missing_checkout_refuses_with_a_window_and_a_non_zero_exit(tmp_path,
                                                                     monkeypatch):
    monkeypatch.delenv("AEGIS_REPO_ROOT", raising=False)
    monkeypatch.setattr(launcher, "find_checkout",
                        lambda *a, **k: {"ok": False, "root": None, "how": None,
                                         "looked_in": ["nowhere"], "markers": []})
    shown: list[dict] = []
    monkeypatch.setattr(launcher, "refuse_window", lambda f: shown.append(f))
    assert launcher.main([]) == 2
    assert shown, "a double-click that finds nothing must not vanish silently"


def test_the_receipt_path_is_in_the_checkout_not_beside_the_exe(tmp_path):
    assert launcher.receipt_path(tmp_path) == (
        tmp_path / "backend" / "data" / "optimus" / "launch_receipt.json")
    assert launcher.log_path(tmp_path).name == "aegis_desktop.log"


@pytest.mark.parametrize("marker", launcher.MARKERS)
def test_each_marker_is_required(tmp_path, marker):
    root = _checkout(tmp_path)
    (root / marker).rmdir()
    assert not launcher._looks_like_checkout(root)
