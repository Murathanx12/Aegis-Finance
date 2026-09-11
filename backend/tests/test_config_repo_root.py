"""`backend.config` resolves its root through `AEGIS_REPO_ROOT`, not `__file__`.

Why this exists (2026-09-10, defect family #14 — "a path that resolves
differently when frozen is a defect family"): inside the packaged app
`__file__` is `<dist>/_internal/backend/config.py`, so `PROJECT_ROOT` resolved
to `_internal`, `load_dotenv(_internal/.env)` found nothing, and
`load_dotenv` on a missing file is a **silent no-op**. Every keyed source was
absent in the .exe and present from source, and nothing said so.

Why a SUBPROCESS (defect #12 of the same day): `backend.config` is imported
once per process and reloading it in-process broke a later identity check in
an unrelated test. A root is decided at import, so it is verified at import —
in a child interpreter whose environment we own outright.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: printed by the child; `PROJECT_ROOT` is the decision, `AEGIS_TEST_MARKER`
#: proves the `.env` beside it was actually READ rather than merely pointed at.
_PROBE = (
    "import json, os;"
    "import backend.config as c;"
    "print(json.dumps({"
    "'root': str(c.PROJECT_ROOT),"
    "'backend_dir': str(c.BACKEND_DIR),"
    "'model_dir': str(c.MODEL_DIR),"
    "'data_dir': str(c.DATA_DIR),"
    "'marker': os.environ.get('AEGIS_TEST_MARKER'),"
    "}))"
)


def _probe(env_overrides: dict[str, str | None]) -> dict:
    env = dict(os.environ)
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    # the child must never inherit the parent's marker, or the test proves nothing
    env.pop("AEGIS_TEST_MARKER", None)
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=str(REPO), env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, f"probe failed: {out.stderr[-2000:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_an_env_root_is_honoured_and_its_dotenv_is_actually_loaded(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / ".env").write_text("AEGIS_TEST_MARKER=42\n", encoding="utf-8")
    got = _probe({"AEGIS_REPO_ROOT": str(tmp_path),
                  "AEGIS_IGNORE_DOTENV": None,   # the point of the test is that dotenv runs
                  "AEGIS_DATA_DIR": None})
    assert Path(got["root"]) == tmp_path.resolve()
    assert got["marker"] == "42", (
        "the .env beside AEGIS_REPO_ROOT was not read — this is the packaged-app defect")
    assert Path(got["backend_dir"]) == (tmp_path / "backend").resolve()
    assert Path(got["data_dir"]) == (tmp_path / "backend" / "data").resolve()
    assert Path(got["model_dir"]) == (tmp_path / "backend" / "models").resolve()


def test_without_the_override_the_root_is_the_source_layout() -> None:
    got = _probe({"AEGIS_REPO_ROOT": None, "AEGIS_IGNORE_DOTENV": "1", "AEGIS_DATA_DIR": None})
    assert Path(got["root"]) == REPO
    assert Path(got["backend_dir"]) == REPO / "backend"
    assert Path(got["model_dir"]) == REPO / "backend" / "models"


def test_a_root_that_is_not_a_directory_falls_back_rather_than_breaking(tmp_path: Path) -> None:
    """A typo'd env var must not silently point the app at nothing."""
    got = _probe({"AEGIS_REPO_ROOT": str(tmp_path / "does-not-exist"),
                  "AEGIS_IGNORE_DOTENV": "1", "AEGIS_DATA_DIR": None})
    assert Path(got["root"]) == REPO
