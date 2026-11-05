"""Import E4 from the repository modules actually present in the API image."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "backend" / "Dockerfile"
E4_BACKEND = (
    "backend/__init__.py",
    "backend/config.py",
    "backend/services/__init__.py",
    "backend/services/owner_decision_bridge.py",
    "backend/services/owner_decision_view.py",
    "backend/services/provisional_event_review.py",
    "backend/services/world_digest.py",
)


def _script_copies(dockerfile: str) -> set[str]:
    scripts: set[str] = set()
    for line in dockerfile.splitlines():
        if not line.startswith("COPY scripts/"):
            continue
        tokens = line.split()[1:-1]
        for token in tokens:
            if re.fullmatch(r"scripts/[A-Za-z0-9_]+\.py", token):
                scripts.add(token)
    return scripts


def test_e4_imports_from_declared_docker_layout(tmp_path: Path) -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY backend/ backend/" in dockerfile
    assert "COPY engine/ engine/" in dockerfile
    scripts = _script_copies(dockerfile)
    assert "scripts/world_digest_provisional.py" in scripts
    assert "scripts/current_exposure_link.py" not in scripts
    assert "scripts/news_station_rss.py" not in scripts

    image = tmp_path / "app"
    for relative in (*E4_BACKEND, *sorted(scripts)):
        source = ROOT / relative
        target = image / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    # The production image copies these static lane configs with backend/.
    for source in (ROOT / "backend/data").glob("*.yaml"):
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
        "from pathlib import Path\n"
        "root=Path.cwd().resolve()\n"
        "assert Path(e4.__file__).resolve().is_relative_to(root)\n"
        "assert Path(hook.__file__).resolve().is_relative_to(root)\n"
        "assert e4.hook is hook\n"
    )
    child = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=image, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert child.returncode == 0, child.stderr[-1000:]
