"""CH-05: a clean checkout can point at the runtime's ONE `.env`.

Why this exists (2026-11-11). The scheduled tasks run from a WIP checkout 269
commits behind main; the switch to a clean checkout of a tagged main commit must
not copy, move or duplicate `.env` (the 2026-08-24 lesson in `backend/config.py`).

(The funnel path is deliberately NOT overridable here: the prepared PC policy epoch
`pc_paper_no_index_2026_10_v1` pins the source of the `IC_FUNNEL_PATH` definition,
and changing it refuses the epoch -- `test_pc_policy_epoch_prepared`.)

Verified in a child interpreter, like `test_config_repo_root.py`: the decision is
made at import, so it is checked at import, in an environment the test owns.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_PROBE = (
    "import json, os;"
    "import backend.config as c;"
    "print(json.dumps({"
    "'dotenv': str(c.DOTENV_PATH),"
    "'root': str(c.PROJECT_ROOT),"
    "'backend_dir': str(c.BACKEND_DIR),"
    "'funnel': str(c.IC_FUNNEL_PATH),"
    "'marker': os.environ.get('AEGIS_TEST_MARKER'),"
    "}))"
)

_KEYS = ("AEGIS_DOTENV_PATH", "AEGIS_IC_FUNNEL_PATH", "AEGIS_REPO_ROOT", "AEGIS_DATA_DIR",
         "AEGIS_TEST_MARKER")


def _run(overrides: dict[str, str | None]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _KEYS}
    env["AEGIS_IGNORE_DOTENV"] = "1"
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return subprocess.run([sys.executable, "-c", _PROBE], cwd=str(REPO), env=env,
                          capture_output=True, text=True, timeout=180)


def _probe(overrides: dict[str, str | None]) -> dict:
    out = _run(overrides)
    assert out.returncode == 0, f"probe failed: {out.stderr[-2000:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_an_explicit_dotenv_path_is_the_file_that_is_loaded(tmp_path: Path) -> None:
    keys = tmp_path / "elsewhere" / "runtime.env"
    keys.parent.mkdir()
    keys.write_text("AEGIS_TEST_MARKER=from-the-declared-file\n", encoding="utf-8")
    got = _probe({"AEGIS_DOTENV_PATH": str(keys), "AEGIS_IGNORE_DOTENV": None})
    assert Path(got["dotenv"]) == keys.resolve()
    assert got["marker"] == "from-the-declared-file", (
        "AEGIS_DOTENV_PATH was resolved but the file it names was not loaded")
    # the code root does not move with it: only the keys file is redirected
    assert Path(got["root"]) == REPO


def test_without_the_variable_the_checkout_dotenv_is_the_default() -> None:
    got = _probe({})
    assert Path(got["dotenv"]) == REPO / ".env"


def test_a_declared_dotenv_that_is_missing_refuses_red(tmp_path: Path) -> None:
    """Falling back to the checkout's own (absent) `.env` would run a scheduled job
    keyless and quietly. A set variable that names no file must exit non-zero."""
    out = _run({"AEGIS_DOTENV_PATH": str(tmp_path / "nope.env"), "AEGIS_IGNORE_DOTENV": None})
    assert out.returncode != 0
    assert "AEGIS_DOTENV_PATH" in out.stderr


def test_a_declared_dotenv_that_is_a_directory_refuses(tmp_path: Path) -> None:
    out = _run({"AEGIS_DOTENV_PATH": str(tmp_path)})
    assert out.returncode != 0
    assert "not a file" in out.stderr
