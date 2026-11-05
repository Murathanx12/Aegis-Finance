"""Import E4 from the repository modules actually present in the API image."""

from __future__ import annotations

import os
from pathlib import Path
from fnmatch import fnmatchcase
import hashlib
import shutil
import subprocess
import sys
import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "backend" / "Dockerfile"
HELPER = "scripts/world_digest_provisional.py"
EXACT_COPY = f"COPY {HELPER} {HELPER}"
CONTEXT_SHA256 = {
    ".dockerignore": "ef4422fb1de3110331dfb825bfa75f6fad2e2beb77ce71b749a1637328386192",
    ".railwayignore": "284b5aa818abb51d6d160e535e21ab671cb0d88a6681e8c377abd5fd19967b35",
}
E4_BACKEND = (
    "backend/__init__.py",
    "backend/config.py",
    "backend/services/__init__.py",
    "backend/services/owner_decision_bridge.py",
    "backend/services/owner_decision_view.py",
    "backend/services/provisional_event_review.py",
    "backend/services/world_digest.py",
)


def _context_includes(relative: str, ignore_file: Path) -> bool:
    """Fail closed on exclusions or pattern forms this narrow check cannot model."""
    if not ignore_file.exists():
        return True
    parts = Path(relative).parts
    targets = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        pattern = raw.strip().replace("\\", "/")
        if not pattern or pattern.startswith("#"):
            continue
        if pattern.startswith("!"):
            continue
        pattern = pattern.strip("/")
        while pattern.startswith("./"):
            pattern = pattern[2:]
        if not pattern:
            continue
        if "**" in pattern or "?" in pattern or "[" in pattern or ".." in pattern.split("/"):
            return False
        # Reject even if a later negation might reinclude it: a future context
        # policy change needs a fresh image-layout review.
        if any(fnmatchcase(target, pattern) or fnmatchcase(target, f"**/{pattern}")
               for target in targets):
            return False
    return True


def _required_context_file(relative: str) -> None:
    assert _context_includes(relative, ROOT / ".dockerignore"), relative
    assert _context_includes(relative, ROOT / ".railwayignore"), relative


def _assert_context_policy_pinned(root: Path) -> None:
    # The fixture models only this reviewed context. Even a benign ignore edit
    # needs a new image-layout review before the regression can pass again.
    assert not (root / "backend/Dockerfile.dockerignore").exists()
    for relative, expected in CONTEXT_SHA256.items():
        content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(content).hexdigest() == expected, relative


@pytest.mark.parametrize("ignore_name", sorted(CONTEXT_SHA256))
def test_context_policy_pin_refuses_edits(tmp_path: Path, ignore_name: str) -> None:
    (tmp_path / "backend").mkdir()
    for relative in CONTEXT_SHA256:
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    _assert_context_policy_pinned(tmp_path)
    with (tmp_path / ignore_name).open("ab") as target:
        target.write(b"\nscripts/./world_digest_provisional.py\n")
    with pytest.raises(AssertionError):
        _assert_context_policy_pinned(tmp_path)
    (tmp_path / ignore_name).unlink()
    with pytest.raises(FileNotFoundError):
        _assert_context_policy_pinned(tmp_path)


def test_dockerfile_specific_ignore_requires_review(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    for relative in CONTEXT_SHA256:
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    (tmp_path / "backend/Dockerfile.dockerignore").write_text("scripts/\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _assert_context_policy_pinned(tmp_path)


@pytest.mark.parametrize("ignore_name", [".dockerignore", ".railwayignore"])
@pytest.mark.parametrize("pattern,relative", [
    ("scripts/world_digest_provisional.py", HELPER),
    ("scripts/", HELPER),
    ("scripts/*.py", HELPER),
    ("**/scripts/**", HELPER),
    ("scripts/**/world_digest_provisional.py", HELPER),
    ("./scripts/world_digest_provisional.py", HELPER),
    ("backend/services/world_digest.py", "backend/services/world_digest.py"),
])
def test_required_context_exclusions_refuse(
    tmp_path: Path, pattern: str, relative: str, ignore_name: str,
) -> None:
    ignore = tmp_path / ignore_name
    ignore.write_text(pattern + "\n", encoding="utf-8")
    assert not _context_includes(relative, ignore)


def test_e4_imports_from_declared_docker_layout(tmp_path: Path) -> None:
    _assert_context_policy_pinned(ROOT)
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY backend/ backend/" in dockerfile
    assert "COPY engine/ engine/" in dockerfile
    # This regression only supports the exact one-file COPY form. A changed
    # destination or broader COPY must be reviewed instead of silently repaired
    # by the test fixture.
    helper_copy_lines = [line.strip() for line in dockerfile.splitlines()
                         if line.lstrip().startswith("COPY ") and HELPER in line]
    assert helper_copy_lines == [EXACT_COPY]
    for relative in (*E4_BACKEND, HELPER):
        _required_context_file(relative)

    image = tmp_path / "app"
    for relative in (*E4_BACKEND, HELPER):
        source = ROOT / relative
        target = image / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    # The production image copies these static lane configs with backend/.
    for source in (ROOT / "backend/data").glob("*.yaml"):
        _required_context_file(source.relative_to(ROOT).as_posix())
        target = image / "backend/data" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    (image / "sitecustomize.py").write_text(
        "import sys\n"
        "def audit(event, args):\n"
        "    if event in ('socket.connect', 'subprocess.Popen'):\n"
        "        raise RuntimeError('FORBIDDEN_IMPORT_SIDE_EFFECT')\n"
        "sys.addaudithook(audit)\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(image),
        AEGIS_REPO_ROOT=str(image),
        AEGIS_DATA_DIR=str(image / "data"),
        AEGIS_IGNORE_DOTENV="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    probe = (
        "import backend.services.owner_decision_bridge as e4\n"
        "import scripts.world_digest_provisional as hook\n"
        "import backend.config as config\n"
        "import backend.services.provisional_event_review as e2\n"
        "import backend.services.owner_decision_view as view\n"
        "import backend.services.world_digest as digest\n"
        "from pathlib import Path\n"
        "root=Path.cwd().resolve()\n"
        "for mod in (e4, hook, config, e2, view, digest):\n"
        "    assert Path(mod.__file__).resolve().is_relative_to(root)\n"
        "assert e4.hook is hook\n"
    )
    child = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=image, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert child.returncode == 0, child.stderr[-1000:]

    # Reproduce the original production failure with the same import probe.
    (image / HELPER).unlink()
    missing = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=image, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert missing.returncode != 0
    assert "ImportError" in missing.stderr
    assert "world_digest_provisional" in missing.stderr
    assert "FORBIDDEN_IMPORT_SIDE_EFFECT" not in missing.stderr
