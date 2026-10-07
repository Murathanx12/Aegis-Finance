"""C15 follow-up (2026-10-07): the production finding was all six legibility/opportunities
endpoints 404ing while `/api/health/full` was 200. The actual cause turned out to be a path
that resolves differently once `AEGIS_DATA_DIR` is set in prod (see `config.PUBLIC_RECEIPTS_DIR`
and `publish_receipts.public_dir`) -- NOT a Dockerfile/.dockerignore omission: the folder is
tracked in git, `COPY backend/ backend/` brings it in, and `.dockerignore` does not exclude it.

That was verified by hand this session; this test makes it a standing, deterministic guard
instead of a one-time check, because "I looked and it was fine" is not a step the next editor
of .dockerignore (adding a broader `data*` or `*.json` line to cut image size, say) will know
to repeat. It parses `backend/Dockerfile`'s `COPY` lines and `.dockerignore`'s patterns and
checks them against every file `backend/data/public_receipts/` currently tracks in git -- the
C15 lesson that a documented step nobody runs is not a step, applied to the image build itself.
Offline: reads two files and runs `git ls-files`; never touches Docker.
"""
from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "backend" / "Dockerfile"
DOCKERIGNORE = REPO / ".dockerignore"
GUARDED_FOLDER = "backend/data/public_receipts"


def _dockerfile_copy_sources() -> list[str]:
    """Every source path a `COPY <src>... <dest>` line brings into the image, as written."""
    srcs: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = line.split()[1:]
        if len(parts) < 2:
            continue
        srcs.extend(parts[:-1])          # every source arg except the final destination arg
    return srcs


def _dockerignore_patterns() -> list[tuple[str, bool]]:
    """(pattern, is_negation) for every non-comment, non-blank line, in file order (later
    lines override earlier ones, same as .gitignore / .dockerignore semantics)."""
    out: list[tuple[str, bool]] = []
    for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        neg = line.startswith("!")
        pat = (line[1:] if neg else line).strip().strip("/")
        out.append((pat, neg))
    return out


def _ignored(rel_path: str, patterns: list[tuple[str, bool]]) -> bool:
    """A pattern with no '/' matches any single path COMPONENT (docker/.gitignore semantics);
    a pattern with '/' matches the path from the repo root (or a prefix of it)."""
    parts = rel_path.split("/")
    ignored = False
    for pat, neg in patterns:
        if "/" in pat:
            hit = fnmatch.fnmatch(rel_path, pat) or rel_path.startswith(pat + "/")
        else:
            hit = any(fnmatch.fnmatch(p, pat) for p in parts)
        if hit:
            ignored = not neg
    return ignored


def _is_under_a_copied_source(rel_path: str, sources: list[str]) -> bool:
    for src in sources:
        s = src.rstrip("/")
        if rel_path == s or rel_path.startswith(s + "/"):
            return True
    return False


def _tracked_public_receipt_files() -> list[str]:
    r = subprocess.run(["git", "ls-files", GUARDED_FOLDER], cwd=str(REPO),
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    files = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    assert files, (f"no tracked file under {GUARDED_FOLDER}/ -- nothing to guard; run "
                    f"`python -m scripts.publish_receipts` and commit the folder first")
    return files


def test_dockerfile_has_a_copy_line_for_the_backend_data_tree():
    sources = _dockerfile_copy_sources()
    assert any(s.rstrip("/") == "backend" for s in sources), (
        f"backend/Dockerfile has no 'COPY backend/ backend/'-shaped line (sources found: {sources}); "
        f"{GUARDED_FOLDER}/ lives under backend/ and needs this COPY to reach the image")


def test_dockerignore_does_not_exclude_public_receipts():
    patterns = _dockerignore_patterns()
    bad = [rel for rel in _tracked_public_receipt_files() if _ignored(rel, patterns)]
    assert not bad, (f"{len(bad)} tracked file(s) under {GUARDED_FOLDER}/ are excluded by "
                      f".dockerignore, e.g. {bad[:5]}: the published copy would never reach the "
                      f"image (patterns: {[p for p, _ in patterns]})")


def test_every_tracked_public_receipt_file_reaches_the_image():
    """End to end: a COPY source covers the path AND no .dockerignore pattern excludes it --
    the actual question the Railway build answers, reproduced without Docker."""
    sources = _dockerfile_copy_sources()
    patterns = _dockerignore_patterns()
    for rel in _tracked_public_receipt_files():
        assert _is_under_a_copied_source(rel, sources), (
            f"{rel} is not under any COPY source in backend/Dockerfile (sources: {sources})")
        assert not _ignored(rel, patterns), f"{rel} is excluded by .dockerignore"
