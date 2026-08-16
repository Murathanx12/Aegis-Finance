"""The dependency boundary around hindsight quantities.

`test_ex_post_scale.py` pins the TYPE: `exposures * scale` raises. This file
pins the ARCHITECTURE: no module the API can reach may import the package the
hindsight lives in, directly or transitively.

The distinction is the whole point. A type error catches a slip — someone
multiplying by an ex-post scale without noticing. It does not catch a decision:
an author who reads the refusal, understands it, and writes
`.for_comparison_only()` anyway because the number needed to line up. The type
cannot argue with intent. A test that fails when the import appears can.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARDED = "backend.services.research_gym.evaluation_only"

#: Everything the running API can reach. Not configuration — if a new
#: deployable surface appears it belongs here, and adding it is the moment to
#: notice whether it should be able to see hindsight (it should not).
DEPLOYABLE_ROOTS = (
    REPO / "backend" / "routers",
    REPO / "backend" / "services",
)

#: Offline research entry points are allowed to import it explicitly — that is
#: what it is for. They are named so the allowance is a list, not a pattern
#: that quietly widens.
ALLOWED = {
    "backend/services/research_gym/evaluation_only/__init__.py",
    "backend/services/research_gym/evaluation_only/ex_post.py",
}


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:                                          # pragma: no cover
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _deployable_files() -> list[Path]:
    out: list[Path] = []
    for root in DEPLOYABLE_ROOTS:
        out.extend(p for p in root.rglob("*.py")
                   if "__pycache__" not in p.parts)
    return out


def test_no_deployable_module_imports_the_hindsight_package():
    offenders = []
    for path in _deployable_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWED:
            continue
        if any(m == GUARDED or m.startswith(GUARDED + ".")
               for m in _imports(path)):
            offenders.append(rel)
    assert not offenders, (
        "these deployable modules import hindsight quantities:\n  "
        + "\n  ".join(offenders)
        + f"\n\n`{GUARDED}` is evaluation-only. If an exposure, weight or "
          "order path needs this number, it needs a version estimable at the "
          "decision time — which is a different quantity, not a different "
          "import.")


def test_the_boundary_test_can_actually_fail():
    """SS47: a guard whose test has never made it fire is not a guard.

    The check above passes today. It would also pass if `_imports` returned
    nothing, or if `_deployable_files` found nothing — so both are exercised
    against a module known to contain the import.
    """
    guarded_init = (REPO / "backend" / "services" / "research_gym"
                    / "evaluation_only" / "__init__.py")
    assert guarded_init.exists()
    mods = _imports(guarded_init)
    assert any(m.startswith(GUARDED) for m in mods), (
        "_imports failed to see an import that is definitely there — the "
        "boundary test would pass vacuously")
    assert len(_deployable_files()) > 50, (
        "_deployable_files found almost nothing; the sweep is not sweeping")


def test_the_allowlist_names_only_files_that_exist():
    """An allowlist entry for a deleted file is a hole nobody can see."""
    missing = [rel for rel in ALLOWED if not (REPO / rel).exists()]
    assert not missing, f"allowlist names files that do not exist: {missing}"


# ── the array variant carries the same refusal ─────────────────────────────

def test_ex_post_array_refuses_broadcasting():
    np = pytest.importorskip("numpy")
    from backend.services.research_gym.evaluation_only import (
        ExPostUsageError, oracle_scale)

    oracle = oracle_scale(np.array([1.0, 2.0, 3.0]),
                          basis="realised vol over the outcome window itself")
    preds = np.array([[1.0], [1.0], [1.0]])
    with pytest.raises(ExPostUsageError):
        _ = preds * oracle
    with pytest.raises(ExPostUsageError):
        _ = oracle * preds
    with pytest.raises(ExPostUsageError):
        _ = np.asarray(oracle)
    with pytest.raises(ExPostUsageError):
        _ = list(oracle)
    # and the named escape works, because a diagnostic must remain possible
    assert np.allclose(oracle.for_comparison_only(), [1.0, 2.0, 3.0])


def test_ex_post_array_may_not_be_constructed_anonymously():
    np = pytest.importorskip("numpy")
    from backend.services.research_gym.evaluation_only import (
        ExPostArray, ExPostUsageError)

    with pytest.raises(ExPostUsageError):
        ExPostArray(np.zeros(3), basis="")
