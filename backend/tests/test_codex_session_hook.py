"""Codex receives useful context even if the shared state builder fails."""

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".codex" / "hooks" / "session_start.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("codex_session_start", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_keeps_state_in_context():
    text = load_hook().context(lambda: {"schema": "stub", "local": {"head": "abc123"}})
    assert json.loads(text.split("\n", 1)[1]) == {
        "schema": "stub", "local": {"head": "abc123"}}


def test_failure_is_explicit_context():
    def broken():
        raise RuntimeError("probe failed")

    assert load_hook().context(broken) == (
        "Aegis session state unavailable: RuntimeError: probe failed")


def test_doc_navigation_does_not_recommend_checkout_mtime_order():
    state = {"docs": {"handoffs_newest_first": ["docs/old-but-touched.md"]}}
    result = json.loads(load_hook().context(lambda: state).split("\n", 1)[1])
    assert result["docs"]["index"] == "docs/INDEX.md"
    assert "old-but-touched" not in json.dumps(result)
    assert "handoffs_newest_first" in state["docs"]  # leave shared input intact


def test_registered_command_resolves_git_root_from_subdirectory(tmp_path):
    repo = tmp_path / "repo with spaces"
    nested = repo / "frontend" / "nested"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], check=True,
                   capture_output=True, timeout=10)
    target = repo / ".codex" / "hooks" / "session_start.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(HOOK.read_bytes())
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "session_state.py").write_text(
        "def build_state():\n    return {'schema': 'registered-command-stub'}\n",
        encoding="utf-8")
    config = json.loads((REPO / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    run = subprocess.run(shlex.split(command), cwd=nested,
                         capture_output=True, text=True, timeout=15, check=True)
    payload = json.loads(run.stdout)["hookSpecificOutput"]
    assert payload["hookEventName"] == "SessionStart"
    assert "registered-command-stub" in payload["additionalContext"]


def test_subprocess_from_foreign_cwd_uses_codex_envelope(tmp_path):
    code = (
        "import runpy, sys; "
        f"sys.path.insert(0, {str(REPO)!r}); "
        "import scripts.session_state as state; "
        "state.build_state = lambda: {'schema': 'offline-stub'}; "
        f"runpy.run_path({str(HOOK)!r}, run_name='__main__')"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                         capture_output=True, text=True, timeout=10, check=True)
    assert run.stderr == ""
    assert json.loads(run.stdout) == {"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "Aegis session state (machine-derived):\n{\n \"schema\": \"offline-stub\"\n}",
    }}
