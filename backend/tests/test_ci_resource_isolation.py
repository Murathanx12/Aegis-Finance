"""Exercise the actual CI shell with tiny recording executables, never replay.

Resource-capped modules must start fresh interpreters before whole-suite
collection, run exactly once, and retain their production guards. This test
does not collect or run the backend suite in a subprocess.
"""
from pathlib import Path
import os
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CAPPED = (
    "backend/tests/test_beta_v1_consumers.py",
    "backend/tests/test_beta_v1_replay.py",
)
FLAGS = ["-m", "not slow", "-q", "-rf", "-p", "pytest_github_actions_annotate_failures"]


def pytest_step():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    return next(step for step in workflow["jobs"]["backend"]["steps"]
                if step.get("name", "").startswith("Pytest (fast suite"))


def bash_executable():
    # Git Bash, rather than a WSL launcher, is the local Windows equivalent of
    # the Ubuntu runner's shell. No dependency installation is required.
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles", "C:/Program Files"),
                     os.environ.get("LOCALAPPDATA", "") + "/Programs"):
            candidate = Path(root) / "Git/bin/bash.exe"
            if candidate.is_file():
                return str(candidate)
        pytest.skip("Git Bash unavailable; CI runs this contract on Ubuntu")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash unavailable")
    return bash


@pytest.mark.parametrize("failure", [None, *CAPPED, "backend/tests/"])
def test_actual_ci_shell_starts_fresh_processes_covers_once_and_keeps_failures(tmp_path, failure):
    step = pytest_step()
    assert step.get("continue-on-error", False) is False
    assert step["env"] == {"AEGIS_IIF1_PREREG_ABSENT_OK": "1"}
    # A recording executable stands in for python. Each invocation really is
    # a distinct process; it records argv and PID without importing pytest,
    # replay, numerical libraries, native code or runtime data.
    fake = tmp_path / "python"
    fake.write_text(
        '#!/usr/bin/env bash\n'
        '{ printf "%s\\t" "$$" "$@"; printf "\\n"; } >> "$CI_PYTEST_LOG"\n'
        'if [[ "$3" == "$CI_FAIL_TARGET" ]]; then exit 5; fi\n',
        encoding="utf-8", newline="\n",
    )
    fake.chmod(0o755)
    script = tmp_path / "actual_ci_step.sh"
    script.write_text(step["run"], encoding="utf-8", newline="\n")
    log = tmp_path / "invocations.tsv"
    env = dict(os.environ, **step["env"],
               PATH=tmp_path.as_posix() + os.pathsep + os.environ["PATH"],
               CI_PYTEST_LOG=log.as_posix(), CI_FAIL_TARGET=failure or "NONE")
    completed = subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-e", script.as_posix()],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode == (1 if failure else 0), completed.stdout + completed.stderr
    calls = [line.rstrip("\t").split("\t") for line in log.read_text().splitlines()]
    assert len(calls) == 3
    assert len({call[0] for call in calls}) == 3
    assert [call[1:] for call in calls] == [
        ["-m", "pytest", CAPPED[0], *FLAGS],
        ["-m", "pytest", CAPPED[1], *FLAGS],
        ["-m", "pytest", "backend/tests/", *("--ignore=" + name for name in CAPPED), *FLAGS],
    ]
    assert all((ROOT / name).is_file() for name in CAPPED)
    # --ignore prevents importing either capped module during the broad
    # collection. No test/node selection or guard override is injected.
    for module in CAPPED:
        assert sum(call[3] == module for call in calls) == 1
        assert calls[-1].count("--ignore=" + module) == 1
    # Verify the partition over every default-discoverable test file without
    # importing/collecting the entire suite (the very contamination at issue).
    # The common -m selector remains identical in all three interpreters.
    files = [p.relative_to(ROOT).as_posix() for p in (ROOT / "backend/tests").rglob("*.py")
             if p.match("test_*.py") or p.match("*_test.py")]
    assert len(files) > len(CAPPED)
    for name in files:
        memberships = 0
        for call in calls:
            selected = call[3]
            ignores = {arg.removeprefix("--ignore=") for arg in call if arg.startswith("--ignore=")}
            memberships += (name == selected or name.startswith(selected.rstrip("/") + "/")) and name not in ignores
        assert memberships == 1, (name, memberships)
